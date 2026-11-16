"""Konfigurasi. DATABASE_URL dibaca dari variabel lingkungan atau, bila tidak ada,
dari Streamlit secrets (.streamlit/secrets.toml / menu Secrets di Streamlit Cloud)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_FILE = ROOT_DIR / "goorame.db"

APP_NAME = "Goorame Mini-ERP"


def _from_secrets(key: str):
    try:
        import streamlit as st
        return st.secrets.get(key)
    except Exception:
        return None


DATABASE_URL = os.environ.get("DATABASE_URL") or _from_secrets("DATABASE_URL") or f"sqlite:///{DB_FILE.as_posix()}"


def _flag(value, default=True) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() not in ("0", "false", "no", "tidak")


# SEED_DEMO_DATA=0 -> database baru hanya berisi bagan akun, 3 rekening (saldo 0), dan akun login.
SEED_DEMO = _flag(os.environ.get("SEED_DEMO_DATA") or _from_secrets("SEED_DEMO_DATA"))
