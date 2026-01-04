from __future__ import annotations
from typing import Optional, Tuple
from ..text_utils import digits_only

def suggest_cfop_for_st(cfop: str, cst: str) -> Tuple[Optional[str], str]:
    """Rules for common mismatches:
    - CST 60 (060) indicates ICMS ST already collected. For saída, CFOP should be 54xx (e.g., 5405/5401).
    - CST 10 (010) indicates tributada com cobrança de ST. CFOP should be 54xx (5401/5403/5405...).
    Heuristic based on original CFOP:
      5101 -> own production => suggest 5401
      5102 -> third-party     => suggest 5405
    Returns (suggested_cfop, rationale).
    """
    cf=digits_only(cfop).zfill(4)[:4]
    cs=digits_only(cst).zfill(3)[:3]
    if cs not in {"060","010"}:
        return None, ""
    if cf in {"5101","5102"}:
        if cf=="5101":
            return "5401", "CST indica ST; CFOP 5101 costuma migrar para 5401 (venda prod. própria sujeita a ST)."
        return "5405", "CST indica ST; CFOP 5102 costuma migrar para 5405 (venda mercadoria de terceiros sujeita a ST)."
    return None, ""

def suggest_cst_for_cfop_st(cfop: str, cst: str) -> Tuple[Optional[str], str]:
    """If CFOP is 54xx but CST isn't ST-related, suggest CST 060 or 010.
    If cfop 5405/5403 -> suggest 060 (mais comum quando ST já recolhido).
    If cfop 5401 -> suggest 010 (tributada com ST) as default.
    """
    cf=digits_only(cfop).zfill(4)[:4]
    cs=digits_only(cst).zfill(3)[:3]
    if not cf.startswith("54"):
        return None, ""
    if cs in {"060","010"}:
        return None, ""
    if cf=="5401":
        return "010", "CFOP 5401 indica operação sujeita a ST; sugerido CST 10 (010) por padrão."
    return "060", "CFOP 54xx indica ST; sugerido CST 60 (060) por padrão (ST já recolhido)."
