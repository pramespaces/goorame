import platform

import pandas as pd
import streamlit as st

from app.core import config
from app.core.database import session_scope
from app.models.user import User
from app.services import operations as ops
from views.common import run_action


def _akun_saya(user):
    st.subheader("Ganti kata sandi")
    with st.form("form_pw", clear_on_submit=True):
        old = st.text_input("Kata sandi lama", type="password")
        new = st.text_input("Kata sandi baru (min. 6 karakter)", type="password")
        again = st.text_input("Ulangi kata sandi baru", type="password")
        if st.form_submit_button("Simpan kata sandi", type="primary"):
            if new != again:
                st.error("Kata sandi baru dan pengulangannya tidak sama.")
            else:
                run_action(ops.change_password, user["id"], old, new, ok="Kata sandi diperbarui.")


def _pengguna(user):
    with session_scope() as db:
        users = db.query(User).order_by(User.username).all()
        rows = [{"Username": u.username, "Nama": u.full_name, "Role": u.role,
                 "Dibuat": u.created_at.strftime("%Y-%m-%d") if u.created_at else "-",
                 "Sandi bawaan": "ya" if ops.uses_default_password(u) else "tidak"} for u in users]
        by_id = {u.id: f"{u.username} ({u.role})" for u in users}
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    left, right = st.columns(2)
    with left:
        with st.form("form_user_new", clear_on_submit=True):
            st.markdown("**Tambah pengguna**")
            username = st.text_input("Username")
            name = st.text_input("Nama tampilan")
            role = st.selectbox("Role", ["PEKERJA", "PEMILIK"])
            pw = st.text_input("Kata sandi awal", type="password")
            if st.form_submit_button("Tambah"):
                run_action(ops.create_user, username, name, role, pw, ok="Pengguna ditambahkan.")
    with right:
        with st.form("form_user_manage"):
            st.markdown("**Kelola pengguna**")
            uid = st.selectbox("Pengguna", list(by_id), format_func=by_id.get)
            new_pw = st.text_input("Kata sandi baru (untuk reset)", type="password")
            c1, c2 = st.columns(2)
            reset = c1.form_submit_button("Reset sandi")
            delete = c2.form_submit_button("Hapus akun")
            if reset:
                run_action(ops.reset_password, uid, new_pw, ok="Kata sandi direset.")
            if delete:
                run_action(ops.delete_user, uid, user["id"], ok="Akun dihapus.")


def _data():
    st.subheader("Cadangan (backup) data")
    url = config.DATABASE_URL
    if url.startswith("sqlite"):
        path = config.DB_FILE
        if path.exists():
            st.download_button("Unduh cadangan database (.db)", path.read_bytes(),
                               f"goorame_backup_{pd.Timestamp.now():%Y%m%d_%H%M}.db", "application/octet-stream")
        st.caption("Simpan berkala. Untuk memulihkan, ganti file goorame.db dengan cadangan ini saat aplikasi mati.")
        st.warning("Memakai SQLite. Jika di-hosting di layanan yang filesystem-nya sementara "
                   "(mis. Streamlit Community Cloud), data bisa hilang saat aplikasi restart. "
                   "Gunakan PostgreSQL lewat DATABASE_URL (lihat panduan hosting).")
    else:
        st.success("Memakai database server (PostgreSQL). Cadangan dilakukan lewat layanan database Anda.")


def _tentang():
    import sqlalchemy
    jenis = "SQLite" if config.DATABASE_URL.startswith("sqlite") else "PostgreSQL"
    st.markdown(f"""
**Goorame Mini-ERP** · versi Python penuh (Streamlit)

| Komponen | Versi |
|---|---|
| Python | {platform.python_version()} |
| Streamlit | {st.__version__} |
| SQLAlchemy | {sqlalchemy.__version__} |
| Pandas | {pd.__version__} |
| Database | {jenis} |
""")


def render(user):
    st.header("Pengaturan")
    owner = user["role"] == "PEMILIK"
    names = ["Akun saya"] + (["Pengguna", "Data & cadangan"] if owner else []) + ["Tentang"]
    tabs = st.tabs(names)
    with tabs[0]:
        _akun_saya(user)
    i = 1
    if owner:
        with tabs[i]:
            _pengguna(user)
        with tabs[i + 1]:
            _data()
        i += 2
    with tabs[i]:
        _tentang()
