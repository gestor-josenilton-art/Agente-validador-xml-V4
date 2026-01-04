import io
import os
import re
import zipfile
from datetime import datetime

df_itens = None  # V3: evita NameError antes do upload/processamento
import pandas as pd
import streamlit as st

from utils.nfe_parser import parse_nfe_xml
from utils.users import ensure_admin, authenticate
from utils.base_legal import ensure_base_legal, load_tables, get_status
from utils.validator import validar_itens

from v3_corrector.correction_engine import apply_corrections
from v3_corrector.xml_rewriter import rewrite_nfe_xml

st.set_page_config(page_title="Agente XML Fiscal — v2", page_icon="🧾", layout="wide")

# Bootstrap admin credentials (override via Streamlit secrets/env)
def _safe_secret(key: str, default: str) -> str:
    """
    Lê segredo do Streamlit (se existir).
    Se não houver secrets.toml (execução local/zip), cai para variável de ambiente ou default show.
    """
    try:
        # st.secrets.get pode disparar FileNotFoundError se não existir secrets.toml
        return st.secrets.get(key, os.environ.get(key, default))
    except FileNotFoundError:
        return os.environ.get(key, default)
    except Exception:
        return os.environ.get(key, default)

ADMIN_USER = _safe_secret("ADMIN_USER", "admin")
ADMIN_PASS = _safe_secret("ADMIN_PASS", "admin123")
ensure_admin(admin_username=ADMIN_USER, admin_password=ADMIN_PASS)

# Ensure base legal templates exist
ensure_base_legal()


def require_login():
    if "auth" not in st.session_state:
        st.session_state.auth = None

    if st.session_state.auth is None:
        st.title("🔒 Login")
        st.caption("Acesso restrito. Solicite seu usuário e senha ao administrador.")
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Usuário")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar")
        if submitted:
            auth = authenticate(username.strip(), password)
            if auth:
                st.session_state.auth = auth
                st.success("Login realizado.")
                st.rerun()
            else:
                st.error("Usuário/senha inválidos ou usuário inativo.")
        st.stop()


require_login()

auth = st.session_state.auth
st.sidebar.markdown("### aplicativo")
st.sidebar.caption(f"Logado como: **{auth['username']}** ({auth.get('role','user')})")
if st.sidebar.button("Sair"):
    st.session_state.auth = None
    st.rerun()

st.title("🧾 Agente Leitor + Validador de XML Fiscal (NF-e) — v2")
st.write(
    "Faça upload de **XML(s) de NF-e** (ou um **.zip** com vários XMLs). "
    "O sistema lê, consolida, e agora **valida CFOP/NCM/CST/CSOSN** com base na **Base Legal** (gerenciável pelo Admin)."
)

uploaded = st.file_uploader("Envie XML(s) ou ZIP", type=["xml", "zip"], accept_multiple_files=True)

colA, colB, colC, colD = st.columns([2, 2, 2, 2])
with colA:
    consolidar_por = st.selectbox(
        "Consolidar por",
        ["xProd + NCM + CFOP", "cProd + NCM + CFOP", "NCM + CFOP", "xProd"],
        index=0,
    )
with colB:
    incluir_cabecalho = st.checkbox("Incorporar aba 'Cabeçalho NF-e'", value=True)
with colC:
    gerar_csv = st.checkbox("Gerar CSV junto (opcional)", value=False)
with colD:
    executar_validacao = st.checkbox("Executar validação fiscal (Base Legal)", value=True)
    aplicar_correcao_v3 = st.checkbox("Aplicar correção automática (V3)", value=False, help="Aplica correções seguras por item (NCM/CFOP/CST) e permite baixar XML corrigido.")

def _read_files(uploaded_files):
    xml_payloads = []
    for uf in uploaded_files or []:
        name = uf.name
        data = uf.read()
        if name.lower().endswith(".zip"):
            try:
                zf = zipfile.ZipFile(io.BytesIO(data))
                for zi in zf.infolist():
                    if zi.filename.lower().endswith(".xml"):
                        xml_payloads.append((zi.filename, zf.read(zi)))
            except Exception as e:
                st.warning(f"Falha ao ler ZIP {name}: {e}")
        elif name.lower().endswith(".xml"):
            xml_payloads.append((name, data))
    return xml_payloads

xml_files = _read_files(uploaded)

if xml_files:
    headers = []
    itens_all = []

    with st.spinner("Lendo XML(s)..."):
        for fname, payload in xml_files:
            try:
                parsed = parse_nfe_xml(payload)
                h = parsed["header"]
                h["arquivo"] = fname
                headers.append(h)
                for it in parsed["items"]:
                    row = {}
                    row.update(h)  # include header fields for traceability
                    row.update(it)
                    itens_all.append(row)
            except Exception as e:
                st.error(f"Erro ao processar {fname}: {e}")

    if not itens_all:
        st.warning("Nenhum item encontrado nos XMLs enviados.")
        st.stop()

    df_itens = pd.DataFrame(itens_all)

    # numeric conversions (best-effort)
    for c in ["qCom", "vUnCom", "vProd", "pICMS", "vICMS", "vNF"]:
        if c in df_itens.columns:
            df_itens[c] = pd.to_numeric(
                df_itens[c].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            )

    # Choose consolidation keys
    if consolidar_por.startswith("xProd +"):
        key_cols = ["xProd", "NCM", "CFOP"]
    elif consolidar_por.startswith("cProd +"):
        key_cols = ["cProd", "NCM", "CFOP"]
    elif consolidar_por.startswith("NCM"):
        key_cols = ["NCM", "CFOP"]
    else:
        key_cols = ["xProd"]

    # Consolidate
    agg = (
        df_itens.groupby(key_cols, dropna=False, as_index=False)
        .agg(
            quantidade=("qCom", "sum"),
            valor_total=("vProd", "sum"),
            valor_unit_medio=("vUnCom", "mean"),
        )
        .sort_values(["valor_total"], ascending=False)
    )
# Validation
df_findings = pd.DataFrame()
df_findings_v3 = pd.DataFrame()
if df_itens is not None:
    df_itens_corrigido = df_itens.copy()
else:
    df_itens_corrigido = None
    st.info("Envie/Processe um XML antes de aplicar correção automática (V3).")
bl_status = get_status()
tables = {}

if executar_validacao:
    with st.spinner("Executando validações..."):
        tables = load_tables()
        # V2 - apontar erros/alertas
        df_findings = validar_itens(df_itens, tables)
        # V3 - sugerir correções (e aplicar se habilitado)
        df_itens_corrigido, df_findings_v3 = apply_corrections(
            df_itens, tables, auto_apply=aplicar_correcao_v3
        )
    # UI tabs
    tabs = st.tabs(["Itens (leitura bruta)", "Consolidado", "Validação", "Base Legal (status)"])

    with tabs[0]:
        st.subheader("Itens (det/prod) — leitura bruta")
        st.dataframe(df_itens, use_container_width=True, height=360)

    with tabs[1]:
        st.subheader("Consolidado")
        st.dataframe(agg, use_container_width=True, height=360)

if aplicar_correcao_v3 and not df_itens_corrigido.empty:
    st.markdown("#### Consolidado (após correção automática V3)")
    try:
        agg2 = (
            df_itens_corrigido.assign(
                vProd_num=pd.to_numeric(df_itens_corrigido.get("vProd", 0), errors="coerce").fillna(0),
                qCom_num=pd.to_numeric(df_itens_corrigido.get("qCom", 0), errors="coerce").fillna(0),
                vUnCom_num=pd.to_numeric(df_itens_corrigido.get("vUnCom", 0), errors="coerce").fillna(0),
            )
            .groupby(group_cols, dropna=False)
            .agg(
                arquivos=("arquivo", "nunique"),
                itens=("nItem", "count"),
                quantidade=("qCom_num", "sum"),
                valor_total=("vProd_num", "sum"),
                valor_unitario=("vUnCom_num", "mean"),
            )
            .sort_values(["valor_total"], ascending=False)
        )
        st.dataframe(agg2, use_container_width=True, height=260)
    except Exception:
        st.warning("Não foi possível gerar o consolidado pós-correção.")

    with tabs[2]:
        st.subheader("Validação fiscal (V2) + Correções (V3)")

        if not executar_validacao:
            st.info("Validação desativada no topo. Marque a opção para executar.")
        else:
            st.markdown("### 📌 Achados (V2) — Erro/Alerta")
            if df_findings.empty:
                st.success("Nenhuma inconsistência encontrada nas regras atuais (ou a base está vazia).")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Erros", int((df_findings["severidade"] == "ERRO").sum()))
                with c2:
                    st.metric("Alertas", int((df_findings["severidade"] == "ALERTA").sum()))
                st.dataframe(df_findings, use_container_width=True, height=260)

            st.markdown("### 🛠️ Correções sugeridas (V3)")
            if df_findings_v3.empty:
                st.info("Nenhuma sugestão de correção gerada (ou faltam bases/itens).")
            else:
                c3, c4, c5 = st.columns(3)
                with c3:
                    st.metric("Sugestões", int(len(df_findings_v3)))
                with c4:
                    st.metric("Auto-corrigíveis", int((df_findings_v3["correcao_automatica"] == True).sum()))
                with c5:
                    st.metric("Aplicadas", int((df_findings_v3["aplicado"] == True).sum()) if "aplicado" in df_findings_v3.columns else 0)

                st.dataframe(df_findings_v3, use_container_width=True, height=320)
                # V3: Correção manual de NCM (quando não há correspondência segura na Tabela NCM)
                try:
                    ncm_table = (tables or {}).get("ncm", pd.DataFrame())
                    allowed_ncms = set()
                    if ncm_table is not None and not ncm_table.empty and "ncm" in ncm_table.columns:
                        allowed_ncms = {re.sub(r"\D+","", str(x)).zfill(8)[:8] for x in ncm_table["ncm"].astype(str).tolist()}
                        allowed_ncms = {n for n in allowed_ncms if n and n != "00000000" and not n.startswith("00")}
                except Exception:
                    allowed_ncms = set()

                df_zero = df_itens_corrigido.copy() if df_itens_corrigido is not None else pd.DataFrame()
                if df_zero is not None and not df_zero.empty:
                    # base para seleção de correções manuais:
                    #  - NCM zerado (00000000)
                    #  - NCM que não consta na Tabela NCM (quando houver)
                    #  - Itens com a MESMA descrição aparecendo com NCMs diferentes no lote (mesmo que o NCM exista na tabela)
                    cand = df_zero.copy()
                    cand["_ncm8"] = cand.get("NCM","").astype(str).apply(lambda x: re.sub(r"\D+","", x).zfill(8)[:8])
                    cand["_desc_key"] = (
                        cand.get("xProd","").astype(str)
                        .str.lower()
                        .str.replace(r"[^a-z0-9]+", " ", regex=True)
                        .str.replace(r"\s+", " ", regex=True)
                        .str.strip()
                    )

                    # descrições com divergência de NCM no mesmo lote
                    try:
                        div_descs = set(
                            cand.groupby("_desc_key")["_ncm8"].nunique(dropna=False)
                            .loc[lambda s: s > 1]
                            .index.tolist()
                        )
                    except Exception:
                        div_descs = set()

                    mask = (cand["_ncm8"] == "00000000") | (cand["_desc_key"].isin(div_descs))
                    if allowed_ncms:
                        mask = mask | (~cand["_ncm8"].isin(list(allowed_ncms)))
                    cand = cand[mask]

                    if not cand.empty:
                        with st.expander("✍️ Informar NCM manualmente (campo Correção sugerida)", expanded=True):
                            st.caption(
                                "Quando o NCM não consta na sua Tabela NCM (base legal), vem como 00000000, ou houver divergência de NCM para a mesma descrição no lote, "
                                "preencha o NCM correto em **Correção sugerida**. "
                                "O sistema só aplica se o código informado existir na Tabela NCM."
                            )
                            edit_df = cand[["arquivo","nItem","xProd","NCM"]].copy() if "arquivo" in cand.columns else cand[["nItem","xProd","NCM"]].copy()
                            edit_df = edit_df.rename(columns={"NCM":"valor_atual"})
                            edit_df["correcao_sugerida"] = ""

                            edited = st.data_editor(
                                edit_df,
                                use_container_width=True,
                                hide_index=True,
                                column_config={
                                    "correcao_sugerida": st.column_config.TextColumn(
                                        "correcao_sugerida",
                                        help="Informe 8 dígitos (ex.: 08119000).",
                                    ),
                                    "valor_atual": st.column_config.TextColumn("valor_atual", disabled=True),
                                    "xProd": st.column_config.TextColumn("xProd", disabled=True),
                                },
                            )

                            if st.button("Aplicar correções manuais (NCM)", type="primary"):
                                applied_ct = 0
                                rejected_ct = 0
                                for i, rowm in edited.iterrows():
                                    ncm8 = re.sub(r"\D+","", str(rowm.get("correcao_sugerida",""))).zfill(8)[:8]
                                    if not ncm8 or ncm8 == "00000000" or ncm8.startswith("00"):
                                        continue
                                    if allowed_ncms and ncm8 not in allowed_ncms:
                                        rejected_ct += 1
                                        continue

                                    # localizar o item correspondente (mesmo arquivo e nItem quando existir)
                                    if "arquivo" in edited.columns and "arquivo" in df_itens_corrigido.columns:
                                        mask = (df_itens_corrigido["arquivo"] == rowm.get("arquivo")) & (df_itens_corrigido["nItem"].astype(str) == str(rowm.get("nItem")))
                                        idxs = df_itens_corrigido.index[mask].tolist()
                                        if idxs:
                                            df_itens_corrigido.at[idxs[0], "NCM"] = ncm8
                                            applied_ct += 1
                                    else:
                                        # fallback por nItem
                                        mask = (df_itens_corrigido["nItem"].astype(str) == str(rowm.get("nItem")))
                                        idxs = df_itens_corrigido.index[mask].tolist()
                                        if idxs:
                                            df_itens_corrigido.at[idxs[0], "NCM"] = ncm8
                                            applied_ct += 1

                                if applied_ct:
                                    st.success(f"NCMs manuais aplicados: {applied_ct}")
                                if rejected_ct:
                                    st.warning(f"NCMs rejeitados (não constam na Tabela NCM): {rejected_ct}")
                    else:
                        pass
                else:
                    pass

# Download corrected XMLs (ZIP) when auto-correction is enabled
            if aplicar_correcao_v3 and not df_findings_v3.empty:
                st.divider()
                st.markdown("### 📦 Saída (V3) — Download dos XMLs corrigidos")

                # build zip in memory
                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                    for fname, payload in xml_files:
                        try:
                            df_o = df_itens[df_itens["arquivo"] == fname].copy()
                            df_c = df_itens_corrigido[df_itens_corrigido["arquivo"] == fname].copy()

                            changes_by_nitem = {}
                            if "nItem" in df_o.columns and "nItem" in df_c.columns:
                                df_o = df_o.set_index("nItem")
                                df_c = df_c.set_index("nItem")

                                common = df_o.index.intersection(df_c.index)
                                for nItem in common:
                                    ch = {}
                                    for col, key in [("NCM","NCM"),("CFOP","CFOP"),("CST_ICMS","CST"),("CSOSN","CSOSN")]:
                                        if col in df_o.columns and col in df_c.columns:
                                            v0 = str(df_o.at[nItem, col] or "")
                                            v1 = str(df_c.at[nItem, col] or "")
                                            if v0.strip() != v1.strip():
                                                ch[key] = v1
                                    if ch:
                                        changes_by_nitem[str(nItem)] = ch

                            corrected = rewrite_nfe_xml(payload, changes_by_nitem) if changes_by_nitem else payload
                            out_name = fname.replace(".xml", "_corrigido.xml")
                            zf.writestr(out_name, corrected)
                        except Exception:
                            # fallback: keep original if something fails for this file
                            zf.writestr(fname, payload)

                zip_buf.seek(0)
                st.download_button(
                    "📥 Baixar ZIP com XMLs corrigidos (V3)",
                    data=zip_buf.getvalue(),
                    file_name=f"xmls_corrigidos_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
                    mime="application/zip",
                )

                # Also allow download of corrected items table
                st.download_button(
                    "📥 Baixar relatório de correções (CSV)",
                    data=df_itens_corrigido.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"itens_corrigidos_v3_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                )
    with tabs[3]:
        st.subheader("Status da Base Legal vigente")
        st.caption("Para substituir a Base Legal, use a página **📚 Admin — Base Legal** no menu lateral (apenas ADMIN).")
        st.write(pd.DataFrame([
            {"tabela": "NCM", "arquivo": "ncm_regras.xlsx", "linhas": bl_status["ncm"].rows, "status": bl_status["ncm"].message},
            {"tabela": "CFOP", "arquivo": "cfop_regras.xlsx", "linhas": bl_status["cfop"].rows, "status": bl_status["cfop"].message},
            {"tabela": "CST/CSOSN", "arquivo": "cst_csosn_regras.xlsx", "linhas": bl_status["cst"].rows, "status": bl_status["cst"].message},
        ]))

    # Downloads
    st.divider()
    st.subheader("Exportações")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        if incluir_cabecalho:
            pd.DataFrame(headers).to_excel(writer, sheet_name="Cabecalho_NFe", index=False)
        df_itens.to_excel(writer, sheet_name="Itens_Bruto", index=False)
        agg.to_excel(writer, sheet_name="Consolidado", index=False)
        if executar_validacao:
            df_findings.to_excel(writer, sheet_name="Validacao", index=False)
    buffer.seek(0)

    st.download_button(
        "📥 Baixar Excel (com abas)",
        data=buffer,
        file_name=f"xml_fiscal_v2_{ts}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    if gerar_csv:
        st.download_button(
            "📥 Baixar CSV (Itens_Bruto)",
            data=df_itens.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"itens_bruto_{ts}.csv",
            mime="text/csv",
        )

else:
    st.info("Envie ao menos 1 XML ou 1 ZIP contendo XMLs para começar.")

st.caption("Admin: gerenciamento de usuários e Base Legal ficam nas páginas do menu lateral (apenas admin).")