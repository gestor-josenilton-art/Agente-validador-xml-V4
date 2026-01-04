from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

@dataclass
class Finding:
    severidade: str  # ERRO / ALERTA
    campo: str       # NCM / CFOP / CST / CSOSN / etc
    mensagem: str
    regra: str = ""
    base: str = ""


def _norm_code(x: str) -> str:
    return str(x or "").strip()


def validar_itens(df_itens: pd.DataFrame, tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Valida itens do XML contra a base legal (tabelas) e também checks de formato.
    Retorna um dataframe de achados (0..n linhas).
    """
    findings: List[Dict[str, str]] = []

    # Se ainda não há itens processados (ex.: após login, antes do upload/processamento do XML),
    # evite exceções e retorne um dataframe vazio.
    if df_itens is None:
        return pd.DataFrame(columns=["chave","nNF","serie","dEmi","nItem","cProd","xProd","severidade","campo","mensagem","regra","base"])

    ncm_tbl = tables.get("ncm", pd.DataFrame()).copy()
    cfop_tbl = tables.get("cfop", pd.DataFrame()).copy()
    cst_tbl = tables.get("cst", pd.DataFrame()).copy()

    # Build lookup sets
    ncm_set = set()
    if not ncm_tbl.empty and "ncm" in ncm_tbl.columns:
        ncm_set = set(ncm_tbl["ncm"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(8))

    cfop_set = set()
    if not cfop_tbl.empty and "cfop" in cfop_tbl.columns:
        cfop_set = set(cfop_tbl["cfop"].astype(str).str.replace(r"\D", "", regex=True).str.zfill(4))

    cst_set = set()
    csosn_set = set()
    if not cst_tbl.empty and {"codigo","tipo"}.issubset(set(cst_tbl.columns)):
        tmp = cst_tbl.copy()
        tmp["tipo"] = tmp["tipo"].astype(str).str.upper().str.strip()
        tmp["codigo"] = tmp["codigo"].astype(str).str.strip()
        cst_set = set(tmp.loc[tmp["tipo"]=="CST","codigo"])
        csosn_set = set(tmp.loc[tmp["tipo"]=="CSOSN","codigo"])

    # Ensure expected cols exist
    for col in ["NCM","CFOP","CST_ICMS","CSOSN","xProd","cProd","nItem","chave","nNF","serie","dEmi"]:
        if col not in df_itens.columns:
            df_itens[col] = ""

    for idx, r in df_itens.iterrows():
        ncm = _norm_code(r.get("NCM",""))
        cfop = _norm_code(r.get("CFOP",""))
        cst = _norm_code(r.get("CST_ICMS",""))
        csosn = _norm_code(r.get("CSOSN",""))

        meta = {
            "chave": _norm_code(r.get("chave","")),
            "nNF": _norm_code(r.get("nNF","")),
            "serie": _norm_code(r.get("serie","")),
            "dEmi": _norm_code(r.get("dEmi","")),
            "nItem": _norm_code(r.get("nItem","")),
            "cProd": _norm_code(r.get("cProd","")),
            "xProd": _norm_code(r.get("xProd","")),
        }

        def add(severidade, campo, mensagem, regra="", base=""):
            row = dict(meta)
            row.update({
                "severidade": severidade,
                "campo": campo,
                "mensagem": mensagem,
                "regra": regra,
                "base": base,
            })
            findings.append(row)

        # Basic format validations
        ncm_digits = "".join([c for c in ncm if c.isdigit()])
        if ncm_digits and len(ncm_digits) != 8:
            add("ALERTA", "NCM", f"NCM com tamanho incomum ({len(ncm_digits)} dígitos): {ncm}", regra="FORMATO_NCM")
        if ncm_digits == "" or ncm_digits == "00000000":
            add("ALERTA", "NCM", f"NCM ausente ou zerado: {ncm or '(vazio)'}", regra="NCM_AUSENTE_OU_ZERADO")

        cfop_digits = "".join([c for c in cfop if c.isdigit()])
        if cfop_digits and len(cfop_digits) != 4:
            add("ALERTA", "CFOP", f"CFOP com tamanho incomum ({len(cfop_digits)} dígitos): {cfop}", regra="FORMATO_CFOP")
        if cfop_digits == "":
            add("ALERTA", "CFOP", "CFOP ausente", regra="CFOP_AUSENTE")

        # CST/CSOSN presence
        if csosn:
            if csosn_set and csosn not in csosn_set:
                add("ERRO", "CSOSN", f"CSOSN '{csosn}' não encontrado na base.", regra="CSOSN_NAO_ENCONTRADO", base="cst_csosn_regras.xlsx")
        elif cst:
            if cst_set and cst not in cst_set:
                add("ERRO", "CST", f"CST '{cst}' não encontrado na base.", regra="CST_NAO_ENCONTRADO", base="cst_csosn_regras.xlsx")
        else:
            add("ALERTA", "CST/CSOSN", "CST/CSOSN ausente no item", regra="CST_CSOSN_AUSENTE")

        # Cross checks with base tables (existence)
        if ncm_set and ncm_digits:
            ncm_norm = ncm_digits.zfill(8)
            if ncm_norm not in ncm_set:
                add("ERRO", "NCM", f"NCM '{ncm_norm}' não encontrado na base.", regra="NCM_NAO_ENCONTRADO", base="ncm_regras.xlsx")

        if cfop_set and cfop_digits:
            cfop_norm = cfop_digits.zfill(4)
            if cfop_norm not in cfop_set:
                add("ERRO", "CFOP", f"CFOP '{cfop_norm}' não encontrado na base.", regra="CFOP_NAO_ENCONTRADO", base="cfop_regras.xlsx")

    return pd.DataFrame(findings)
