from __future__ import annotations
import re
import unicodedata

def norm_text(s: str) -> str:
    s = str(s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s

def digits_only(s: str) -> str:
    return re.sub(r"\D+", "", str(s or ""))
