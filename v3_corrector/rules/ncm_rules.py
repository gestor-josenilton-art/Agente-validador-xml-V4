from __future__ import annotations
from typing import Optional
import pandas as pd
from ..text_utils import norm_text, digits_only

def suggest_ncm_from_description(desc: str, ncm_table: pd.DataFrame) -> Optional[str]:
    """Heuristic: tries to find a NCM by description match against base table.
    Expects columns: ncm, descricao (lowercase normalized in load_tables()).
    """
    if ncm_table is None or ncm_table.empty:
        return None
    if "ncm" not in ncm_table.columns:
        return None
    # try to use descricao column if present
    desc_norm = norm_text(desc)
    if not desc_norm:
        return None

    if "descricao" in ncm_table.columns:
        # score rows by token overlap
        tokens = [t for t in desc_norm.split(" ") if len(t) >= 4]
        if not tokens:
            tokens = desc_norm.split(" ")
        best = (0, None)
        for _, row in ncm_table.iterrows():
            cand_desc = norm_text(row.get("descricao",""))
            if not cand_desc:
                continue
            score = sum(1 for t in tokens if t in cand_desc)
            if score > best[0]:
                ncm = digits_only(row.get("ncm","")).zfill(8)[:8]
                best = (score, ncm)
        if best[0] > 0:
            return best[1]
    return None
