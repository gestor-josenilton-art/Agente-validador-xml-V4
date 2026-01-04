from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]  # project root (agente_leitor_xml_fiscal)
DATA_DIR = BASE_DIR / "data"
BL_DIR = DATA_DIR / "base_legal"
CURRENT_DIR = BL_DIR / "current"
HISTORY_DIR = BL_DIR / "history"

# Expected filenames in CURRENT_DIR
FILES = {
    "ncm": "ncm_regras.xlsx",
    "cfop": "cfop_regras.xlsx",
    "cst": "cst_csosn_regras.xlsx",
}

# Required columns (case-insensitive)
REQUIRED_COLS = {
    "ncm": ["ncm", "descricao"],
    "cfop": ["cfop", "descricao"],
    "cst": ["codigo", "tipo", "descricao"],  # tipo: CST or CSOSN
}

@dataclass
class BaseLegalStatus:
    ok: bool
    message: str
    rows: int = 0
    path: Optional[str] = None


def ensure_base_legal() -> None:
    """Create folders and starter templates if missing."""
    CURRENT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # Minimal starter datasets (you can replace via Admin upload)
    if not (CURRENT_DIR / FILES["ncm"]).exists():
        df = pd.DataFrame([
            {"ncm": "00000000", "descricao": "PLACEHOLDER - Substitua pela sua base NCM/TIPI"},
        ])
        df.to_excel(CURRENT_DIR / FILES["ncm"], index=False)

    if not (CURRENT_DIR / FILES["cfop"]).exists():
        df = pd.DataFrame([
            {"cfop": "5102", "descricao": "Venda de mercadoria adquirida ou recebida de terceiros"},
        ])
        df.to_excel(CURRENT_DIR / FILES["cfop"], index=False)

    if not (CURRENT_DIR / FILES["cst"]).exists():
        df = pd.DataFrame([
            {"codigo": "00", "tipo": "CST", "descricao": "Tributada integralmente"},
            {"codigo": "102", "tipo": "CSOSN", "descricao": "Tributada pelo Simples Nacional sem permissão de crédito"},
        ])
        df.to_excel(CURRENT_DIR / FILES["cst"], index=False)


def _read_excel(path: Path) -> pd.DataFrame:
    return pd.read_excel(path, dtype=str).fillna("")


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def load_tables() -> Dict[str, pd.DataFrame]:
    """Load base legal tables. Always returns keys ncm/cfop/cst (possibly empty)."""
    ensure_base_legal()
    tables: Dict[str, pd.DataFrame] = {}
    for key, fname in FILES.items():
        path = CURRENT_DIR / fname
        try:
            df = _read_excel(path)
            df = _norm_cols(df)
        except Exception:
            df = pd.DataFrame()
        tables[key] = df
    return tables


def validate_table(key: str, df: pd.DataFrame) -> Tuple[bool, str]:
    """Validate required columns for a given table."""
    df = _norm_cols(df)
    req = REQUIRED_COLS[key]
    missing = [c for c in req if c not in df.columns]
    if missing:
        return False, f"Colunas obrigatórias ausentes: {', '.join(missing)}"
    return True, "OK"


def save_uploaded_table(key: str, uploaded_bytes: bytes) -> BaseLegalStatus:
    """
    Save an uploaded XLSX as the current table and keep a timestamped backup.
    Returns status with message for UI.
    """
    ensure_base_legal()
    fname = FILES[key]
    tmp_path = CURRENT_DIR / f"__tmp__{fname}"

    try:
        tmp_path.write_bytes(uploaded_bytes)
        df = pd.read_excel(tmp_path, dtype=str).fillna("")
        ok, msg = validate_table(key, df)
        if not ok:
            tmp_path.unlink(missing_ok=True)
            return BaseLegalStatus(ok=False, message=msg)

        # Backup current (if exists)
        cur_path = CURRENT_DIR / fname
        ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
        if cur_path.exists():
            backup = HISTORY_DIR / f"{ts}__{fname}"
            cur_path.replace(backup)

        # Move tmp into place
        tmp_path.replace(cur_path)
        return BaseLegalStatus(ok=True, message="Base atualizada com sucesso.", rows=len(df), path=str(cur_path))
    except Exception as e:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return BaseLegalStatus(ok=False, message=f"Falha ao salvar/ler Excel: {e}")


def get_status() -> Dict[str, BaseLegalStatus]:
    """Return basic status about current base files."""
    ensure_base_legal()
    out: Dict[str, BaseLegalStatus] = {}
    for key, fname in FILES.items():
        p = CURRENT_DIR / fname
        if not p.exists():
            out[key] = BaseLegalStatus(ok=False, message="Arquivo não encontrado.")
            continue
        try:
            df = pd.read_excel(p, dtype=str)
            out[key] = BaseLegalStatus(ok=True, message="OK", rows=len(df), path=str(p))
        except Exception as e:
            out[key] = BaseLegalStatus(ok=False, message=f"Erro ao ler: {e}", path=str(p))
    return out
