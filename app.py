"""Goorame Mini-ERP — versi Python penuh (Streamlit).

Jalankan:  python -m streamlit run app.py
"""
import streamlit as st
from PIL import Image

from app.core import config
from app.core.database import init_db, session_scope
from app.services import operations as ops
from views import (akuntansi, buku_besar, dashboard, kas, kolam, laporan, pengaturan, pengeluaran,
                   penjualan, utang)
from views.common import ASSETS, inject_css, show_flash

st.set_page_config(page_title="Goorame", page_icon=Image.open(ASSETS / "favicon.png"), layout="wide")

# (judul menu, modul, hanya pemilik?)
MENU = [
    ("Dashboard", dashboard, False),
    ("Stok Kolam", kolam, False),
    ("Penjualan", penjualan, True),
    ("Pengeluaran", pengeluaran, True),
    ("Utang & Piutang", utang, True),
    ("Kas & Bank", kas, True),
    ("Jurnal Umum", akuntansi, True),
    ("Buku Besar", buku_besar, True),
    ("Laporan", laporan, True),
    ("Pengaturan", pengaturan, False),
]


@st.cache_resource
def _bootstrap():
    init_db()
    return True


def config_banner():
    if config.SECRETS_PROBLEM:
        st.error(f"Konfigurasi database bermasalah: {config.SECRETS_PROBLEM} "
                 "Aplikasi sementara memakai SQLite, sehingga data bisa hilang saat restart.", icon="🚨")


def login_screen():
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        config_banner()
        st.image(str(ASSETS / "logo.png"), width=260)
        st.markdown("<h1 class='login-title'>Goorame</h1>"
                    "<p class='login-sub'>Sistem informasi akuntansi &amp; budidaya ikan gurame</p>",
                    unsafe_allow_html=True)
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Kata sandi", type="password")
            if st.form_submit_button("Masuk", type="primary", width="stretch"):
                try:
                    with session_scope() as db:
                        u = ops.login(db, username, password)
                        st.session_state["user"] = {
                            "id": u.id, "name": u.full_name, "role": u.role,
                            "default_pw": ops.uses_default_password(u)}
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))


def main():
    inject_css()
    _bootstrap()
    user = st.session_state.get("user")
    if not user:
        login_screen()
        return

    visible = [m for m in MENU if user["role"] == "PEMILIK" or not m[2]]
    with st.sidebar:
        _, c, _ = st.columns([1, 2, 1])
        c.image(str(ASSETS / "logo.png"), width="stretch")
        st.markdown(f"**{user['name']}** · {user['role'].title()}")
        page = st.radio("Menu", [m[0] for m in visible], label_visibility="collapsed")
        if st.button("Keluar", width="stretch"):
            st.session_state.clear()
            st.rerun()

    config_banner()
    if user.get("default_pw"):
        st.warning("Anda masih memakai kata sandi bawaan. Ganti di menu Pengaturan → Akun saya.", icon="🔐")
    show_flash()
    dict((m[0], m[1]) for m in visible)[page].render(user)
    st.markdown("<div class='goorame-footer'>Goorame Mini-ERP · dibuat dengan Python &amp; Streamlit</div>",
                unsafe_allow_html=True)


main()
