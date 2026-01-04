from __future__ import annotations
from typing import Dict, List, Tuple, Any
import pandas as pd

from .finding import FindingV3
from .text_utils import digits_only, norm_text
from .rules.ncm_rules import suggest_ncm_from_description
from .rules.product_consistency import build_desc_to_ncm_mode
from .rules.cfop_cst_rules import suggest_cfop_for_st, suggest_cst_for_cfop_st

def apply_corrections(
    df_itens: pd.DataFrame,
    tables: Dict[str, pd.DataFrame],
    auto_apply: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return (df_corrigido, df_findings_v3).
    - Sugere correções e, se auto_apply=True, aplica correções seguras por item.
    """
    if df_itens is None or df_itens.empty:
        return df_itens, pd.DataFrame()

    df = df_itens.copy()
    findings: List[FindingV3] = []

    ncm_table = (tables or {}).get("ncm", pd.DataFrame())
    allowed_ncms = set()
    try:
        if ncm_table is not None and not ncm_table.empty and 'ncm' in ncm_table.columns:
            allowed_ncms = {digits_only(x).zfill(8)[:8] for x in ncm_table['ncm'].astype(str).tolist()}
            # Filtra NCMs inválidos (ex.: começando com '00' ou zerado)
            allowed_ncms = {n for n in allowed_ncms if n and n != '00000000' and not n.startswith('00')}
    except Exception:
        allowed_ncms = set()
    desc_to_mode = build_desc_to_ncm_mode(df)

    # --- Divergência: mesma descrição com NCMs diferentes no lote (mesmo quando não há recorrência forte)
    try:
        tmp_div = df.copy()
        tmp_div["_desc_norm"] = tmp_div.get("xProd","").apply(norm_text)
        tmp_div["_ncm8"] = tmp_div.get("NCM","").apply(lambda x: digits_only(x).zfill(8)[:8])
        # mapeia descrição -> conjunto de NCMs distintos (inclui inválidos diferentes de vazio)
        desc_to_unique_ncms = {}
        for d, grp in tmp_div.groupby("_desc_norm"):
            vals = {str(v) for v in grp["_ncm8"].tolist() if str(v).strip()}
            # ignora vazio e 00000000 isolado
            vals = {v for v in vals if v and v != "00000000"}
            if len(vals) > 1 and len(grp) >= 2:
                desc_to_unique_ncms[d] = vals
    except Exception:
        desc_to_unique_ncms = {}

    def add(**kwargs):
        findings.append(FindingV3(**kwargs))

    for idx, row in df.iterrows():
        desc = row.get("xProd","")
        desc_norm = norm_text(desc)
        ncm_raw = row.get("NCM","")
        cfop_raw = row.get("CFOP","")
        cst_raw = row.get("CST_ICMS","") or ""
        csosn_raw = row.get("CSOSN","") or ""

        # --- NCM: 00000000 / vazio
        ncm_digits = digits_only(ncm_raw).zfill(8)[:8]
        # --- NCM: informado mas não consta na tabela (quando disponível)
        if allowed_ncms and ncm_digits not in {'00000000',''} and ncm_digits not in allowed_ncms:
            add(
                severidade='ERRO',
                campo='NCM',
                problema='NCM não consta na Tabela NCM',
                causa='Código no XML não existe na base legal informada',
                valor_atual=ncm_digits,
                correcao_sugerida='',
                base_legal='Sem correspondência na Tabela NCM (ncm_regras.xlsx)',
                correcao_automatica=False,
                aplicado=False,
            )

        # ALERTA: mesma descrição com NCMs diferentes no lote (sem recorrência forte)
        if desc_norm and (desc_norm in desc_to_unique_ncms) and (desc_norm not in desc_to_mode):
            add(
                severidade="ALERTA",
                campo="NCM",
                problema="Mesma descrição com NCM diferente em itens do lote",
                causa="Itens com mesma descrição aparecem com NCMs distintos no mesmo processamento",
                valor_atual=ncm_digits or "",
                correcao_sugerida="",
                base_legal="Divergência por comparação no lote (itens do XML)",
                correcao_automatica=False,
                aplicado=False,
            )
        if ncm_digits in {"00000000",""}:
            sug_table = suggest_ncm_from_description(desc, ncm_table)
            sug_mode = desc_to_mode.get(desc_norm)
            sug = sug_table or sug_mode
            # Validação: só aceite NCM existente na Tabela NCM (quando disponível)
            if sug:
                sug8 = digits_only(sug).zfill(8)[:8]
                # Rejeita NCMs inválidos (chapters começam em 01..97; '00' é inválido)
                if sug8.startswith('00') or sug8 == '00000000':
                    sug = None
                elif allowed_ncms and sug8 not in allowed_ncms:
                    sug = None
            if sug:
                aplicado = False
                if auto_apply:
                    df.at[idx,"NCM"] = sug
                    aplicado = True
                add(
                    severidade="ERRO",
                    campo="NCM",
                    problema="NCM inválido (00000000) ou ausente",
                    causa="Cadastro incompleto ou item sem NCM no XML",
                    valor_atual=ncm_digits or "",
                    correcao_sugerida=sug,
                    base_legal=("Tabela NCM (ncm_regras.xlsx)" if sug_table else "Padronização por recorrência (itens do lote)"),
                    correcao_automatica=True,
                    aplicado=aplicado,
                )
            else:
                add(
                    severidade="ERRO",
                    campo="NCM",
                    problema="NCM inválido (00000000) ou ausente",
                    causa="Cadastro incompleto e não foi possível inferir pela base",
                    valor_atual=ncm_digits or "",
                    correcao_sugerida="Preencher NCM correto (manual) / atualizar base NCM",
                    base_legal=("Tabela NCM (ncm_regras.xlsx)" if sug_table else "Padronização por recorrência (itens do lote)"),
                    correcao_automatica=False,
                    aplicado=False,
                )

        # --- Mesmo produto com NCM diferente (consistência por descrição)
        if desc_norm and desc_norm in desc_to_mode:
            mode_ncm = desc_to_mode[desc_norm]
            if ncm_digits and ncm_digits != "00000000" and mode_ncm and ncm_digits != mode_ncm:
                aplicado = False
                if auto_apply:
                    df.at[idx,"NCM"] = mode_ncm
                    aplicado = True
                add(
                    severidade="ALERTA",
                    campo="NCM",
                    problema="Mesma descrição com NCM diferente em outros itens",
                    causa="Cadastro divergente para o mesmo produto",
                    valor_atual=ncm_digits,
                    correcao_sugerida=mode_ncm,
                    base_legal="Padronização por recorrência (itens do lote)",
                    correcao_automatica=True,
                    aplicado=aplicado,
                )
            else:
                # Sem correspondência válida na tabela: não sugere automaticamente
                add(
                    severidade="ERRO",
                    campo="NCM",
                    problema="NCM inválido (00000000) ou ausente",
                    causa="Cadastro incompleto ou item sem NCM no XML",
                    valor_atual=ncm_digits or "",
                    correcao_sugerida="",
                    base_legal="Sem correspondência na Tabela NCM (ncm_regras.xlsx)",
                    correcao_automatica=False,
                    aplicado=False,
                )

        # --- CFOP x CST (ICMS) - foco nos casos 5101/5102 com 060/010
        if cst_raw:
            sug_cfop, why = suggest_cfop_for_st(cfop_raw, cst_raw)
            if sug_cfop:
                aplicado=False
                if auto_apply:
                    df.at[idx,"CFOP"] = sug_cfop
                    aplicado=True
                add(
                    severidade="ERRO",
                    campo="CFOP/CST",
                    problema="CFOP incompatível com CST informado",
                    causa=why or "Incompatibilidade CFOP x CST (ST)",
                    valor_atual=f"CFOP={digits_only(cfop_raw).zfill(4)[:4]} | CST={digits_only(cst_raw).zfill(3)[:3]}",
                    correcao_sugerida=f"CFOP={sug_cfop} (manter CST={digits_only(cst_raw).zfill(3)[:3]})",
                    base_legal="Regra operacional (ST) – ajustar CFOP 54xx quando CST 060/010",
                    correcao_automatica=True,
                    aplicado=aplicado,
                )

        # Se CFOP 54xx e CST não ST-related, sugerir CST
        if cfop_raw:
            sug_cst, why2 = suggest_cst_for_cfop_st(cfop_raw, cst_raw)
            if sug_cst:
                aplicado=False
                if auto_apply:
                    df.at[idx,"CST_ICMS"] = sug_cst
                    aplicado=True
                add(
                    severidade="ALERTA",
                    campo="CST",
                    problema="CST possivelmente incompatível com CFOP 54xx",
                    causa=why2 or "Incompatibilidade CFOP 54xx x CST",
                    valor_atual=f"CFOP={digits_only(cfop_raw).zfill(4)[:4]} | CST={digits_only(cst_raw).zfill(3)[:3] or ''}",
                    correcao_sugerida=f"CST={sug_cst}",
                    base_legal="Regra operacional (ST) – CST 060/010 quando CFOP 54xx",
                    correcao_automatica=True,
                    aplicado=aplicado,
                )

        # --- CST/CSOSN ausente (sugestão: depende regime, apenas alerta)
        if not cst_raw and not csosn_raw:
            add(
                severidade="ALERTA",
                campo="CST/CSOSN",
                problema="CST/CSOSN ausente",
                causa="Item sem tributação ICMS identificada no XML",
                valor_atual="",
                correcao_sugerida="Revisar tributação do item (CST para Regime Normal / CSOSN para Simples)",
                base_legal="Tabela CST/CSOSN (cst_csosn_regras.xlsx)",
                correcao_automatica=False,
                aplicado=False,
            )

    df_find = pd.DataFrame([f.__dict__ for f in findings])
    # sort
    if not df_find.empty:
        sev_order={"ERRO":0,"ALERTA":1}
        df_find["_o"]=df_find["severidade"].map(lambda x: sev_order.get(x,9))
        df_find=df_find.sort_values(["_o","campo"]).drop(columns=["_o"])
    return df, df_find
