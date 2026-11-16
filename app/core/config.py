"""Konfigurasi. DATABASE_URL dibaca dari variabel lingkungan atau, bila tidak ada,
dari Streamlit secrets (.streamlit/secrets.toml / menu Secrets di Streamlit Cloud)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DB_FILE = ROOT_DIR / "goorame.db"

APP_NAME = "Goorame Mini-ERP"


SECRETS_PROBLEM = None   # pesan bila file Secrets rusak (tanpa nilai rahasia)
SECRET_KEYS = []         # hanya NAMA kunci yang terbaca, untuk diagnosa


def _from_secrets(key: str):
    global SECRETS_PROBLEM
    try:
        import streamlit as st
        value = st.secrets.get(key)
        SECRET_KEYS[:] = list(st.secrets.keys())
        return value
    except Exception as exc:
        if "pars" in str(exc).lower():
            SECRETS_PROBLEM = ("Format Secrets tidak valid (biasanya nilai tidak diberi tanda kutip dua, "
                               "contoh benar: DATABASE_URL = \"postgresql://...\").")
        return None


DATABASE_URL = os.environ.get("DATABASE_URL") or _from_secrets("DATABASE_URL") or f"sqlite:///{DB_FILE.as_posix()}"


def _flag(value, default=True) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() not in ("0", "false", "no", "tidak")


# SEED_DEMO_DATA=0 -> database baru hanya berisi bagan akun, 3 rekening (saldo 0), dan akun login.
SEED_DEMO = _flag(os.environ.get("SEED_DEMO_DATA") or _from_secrets("SEED_DEMO_DATA"))
