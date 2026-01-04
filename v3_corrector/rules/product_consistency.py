from __future__ import annotations
from typing import Dict, Optional
import pandas as pd
from ..text_utils import norm_text, digits_only

def mode(series: pd.Series) -> Optional[str]:
    if series is None or series.empty:
        return None
    vc = series.value_counts(dropna=True)
    if vc.empty:
        return None
    return str(vc.index[0])

def build_desc_to_ncm_mode(df: pd.DataFrame) -> Dict[str,str]:
    """Map normalized product description -> most frequent NCM (8 digits).
    Conservative: only returns a mode when there is a real recurrence (>=2 itens)
    and dominance (>=60%). This avoids false 'recorrência' when all NCMs are unique.
    """
    mapping = {}
    if df is None or df.empty:
        return mapping
    if "xProd" not in df.columns or "NCM" not in df.columns:
        return mapping

    tmp = df.copy()
    tmp["_desc"] = tmp["xProd"].apply(norm_text)
    tmp["_ncm"] = tmp["NCM"].apply(lambda x: digits_only(x).zfill(8)[:8])

    for d, grp in tmp.groupby("_desc"):
        vc = grp["_ncm"].value_counts(dropna=True)
        if vc.empty:
            continue
        ncm_mode = str(vc.index[0])
        cnt_mode = int(vc.iloc[0])
        cnt_total = int(vc.sum())

        # precisa de recorrência real
        if cnt_total < 2 or cnt_mode < 2:
            continue

        # precisa de dominância
        if (cnt_mode / cnt_total) < 0.60:
            continue

        # filtra ncm inválido
        if not ncm_mode or ncm_mode == "00000000" or ncm_mode.startswith("00"):
            continue

        mapping[d] = ncm_mode

    return mapping
