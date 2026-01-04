import json
import os
from pathlib import Path
from typing import Dict, Any
from .crypto import hash_password, verify_password

DEFAULT_USERS_FILE = Path(__file__).resolve().parents[2] / "data" / "users.json"

def load_users(path: Path = DEFAULT_USERS_FILE) -> Dict[str, Any]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # default admin user will be created by bootstrap in app startup
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"users": {}}, f, ensure_ascii=False, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_users(data: Dict[str, Any], path: Path = DEFAULT_USERS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def ensure_admin(path: Path = DEFAULT_USERS_FILE, admin_username: str = "admin", admin_password: str = "admin123") -> None:
    """Create admin user if missing. Use secrets/env for password in production."""
    data = load_users(path)
    users = data.setdefault("users", {})
    if admin_username not in users:
        users[admin_username] = {
            "password_hash": hash_password(admin_password),
            "role": "admin",
            "active": True,
            "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z"
        }
        save_users(data, path)

def authenticate(username: str, password: str, path: Path = DEFAULT_USERS_FILE):
    data = load_users(path)
    u = data.get("users", {}).get(username)
    if not u or not u.get("active", True):
        return None
    if verify_password(password, u.get("password_hash", "")):
        return {"username": username, "role": u.get("role", "user")}
    return None

def add_user(username: str, password: str, role: str = "user", active: bool = True, path: Path = DEFAULT_USERS_FILE) -> None:
    data = load_users(path)
    users = data.setdefault("users", {})
    if username in users:
        raise ValueError("Usuário já existe.")
    users[username] = {
        "password_hash": hash_password(password),
        "role": role,
        "active": active,
        "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z"
    }
    save_users(data, path)

def set_user_active(username: str, active: bool, path: Path = DEFAULT_USERS_FILE) -> None:
    data = load_users(path)
    users = data.setdefault("users", {})
    if username not in users:
        raise ValueError("Usuário não encontrado.")
    users[username]["active"] = active
    save_users(data, path)

def list_users(path: Path = DEFAULT_USERS_FILE):
    data = load_users(path)
    out = []
    for uname, u in data.get("users", {}).items():
        out.append({
            "username": uname,
            "role": u.get("role","user"),
            "active": u.get("active", True),
            "created_at": u.get("created_at","")
        })
    return out

# --- Streamlit helpers (UI access control) ---

def require_admin():
    """Stop execution if current session is not admin."""
    try:
        import streamlit as st
    except Exception:
        return
    auth = st.session_state.get('auth')
    if not auth or auth.get('role') != 'admin':
        st.error('Acesso restrito: apenas ADMIN.')
        st.stop()
