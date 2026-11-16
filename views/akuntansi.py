from datetime import date

import pandas as pd
import streamlit as st

from app.core.database import session_scope
from app.models.accounting import ChartOfAccount
from app.services import operations as ops
from app.services.accounting_service import JournalLine, list_journals
from views.common import download_buttons, money_cfg, period_picker, rows_to_df, run_action, rupiah

TEMPLATES = {
    "— kosong —": [],
    "Setoran modal pemilik": [("1110", "D"), ("3100", "K")],
    "Prive (pengambilan pemilik)": [("3300", "D"), ("1130", "K")],
    "Bayar gaji dari kas kecil": [("6110", "D"), ("1130", "K")],
    "Bayar listrik dari bank BCA": [("6120", "D"), ("1110", "K")],
    "Beban BBM & transportasi": [("6130", "D"), ("1130", "K")],
    "Perawatan kolam & peralatan": [("6140", "D"), ("1130", "K")],
    "Kerugian ikan mati": [("5120", "D"), ("1180", "K")],
}


def _manual_journal(coa_labels: dict):
    st.subheader("Jurnal manual")
    labels = list(coa_labels.values())
    tpl = st.selectbox("Template cepat", list(TEMPLATES), key="j_tpl")
    rows = [{"Akun": coa_labels.get(code), "Debit": 0.0, "Kredit": 0.0} for code, _ in TEMPLATES[tpl]] \
        or [{"Akun": None, "Debit": 0.0, "Kredit": 0.0}] * 2
    with st.form("form_journal"):
        c1, c2 = st.columns([1, 3])
        d = c1.date_input("Tanggal", date.today())
        desc = c2.text_input("Keterangan", placeholder="mis. Setoran modal tambahan")
        edited = st.data_editor(
            pd.DataFrame(rows), num_rows="dynamic", width="stretch", key=f"journal_editor_{tpl}",
            column_config={
                "Akun": st.column_config.SelectboxColumn("Akun", options=labels, required=True),
                "Debit": st.column_config.NumberColumn("Debit", min_value=0.0, format="%.0f"),
                "Kredit": st.column_config.NumberColumn("Kredit", min_value=0.0, format="%.0f"),
            })
        total_d, total_k = float(edited["Debit"].fillna(0).sum()), float(edited["Kredit"].fillna(0).sum())
        st.caption(f"Total debit {rupiah(total_d)} · total kredit {rupiah(total_k)} · "
                   + ("seimbang" if round(total_d, 2) == round(total_k, 2) and total_d > 0 else "BELUM seimbang"))
        if st.form_submit_button("Simpan jurnal", type="primary"):
            by_label = {v: k for k, v in coa_labels.items()}
            lines = [JournalLine(by_label[r["Akun"]], debit=float(r["Debit"] or 0), credit=float(r["Kredit"] or 0))
                     for _, r in edited.iterrows() if r["Akun"] in by_label and (r["Debit"] or r["Kredit"])]
            run_action(ops.create_manual_journal, d.isoformat(), desc, lines, ok="Jurnal manual tersimpan.")


def render(user):
    st.header("Jurnal Umum")
    with session_scope() as db:
        coas = db.query(ChartOfAccount).order_by(ChartOfAccount.code).all()
        coa_df = rows_to_df(coas, {"code": "Kode", "name": "Nama akun", "category": "Kategori",
                                   "normal_balance": "Saldo normal", "description": "Keterangan"})
        coa_labels = {c.code: f"{c.code} — {c.name}" for c in coas}

    t_list, t_new, t_coa = st.tabs(["Daftar jurnal", "Jurnal manual", "Bagan akun (COA)"])

    with t_list:
        start, end = period_picker("jurnal", default="Semua periode")
        q = st.text_input("Cari (keterangan / nomor jurnal / referensi)", key="jurnal_q")
        with session_scope() as db:
            journals = list_journals(db, start, end, q)
        types = sorted({j["type"] for j in journals})
        pick = st.multiselect("Jenis transaksi", types, key="jurnal_types")
        if pick:
            journals = [j for j in journals if j["type"] in pick]
        st.caption(f"{len(journals)} jurnal ditampilkan (maks. 300 terbaru) · total nilai "
                   f"{rupiah(sum(j['total'] for j in journals))}")
        flat = [{"No. Jurnal": j["no"], "Tanggal": j["date"], "Keterangan": j["desc"], "Jenis": j["type"],
                 "Kode akun": i[0], "Akun": i[1], "Debit": i[2], "Kredit": i[3]}
                for j in journals for i in j["items"]]
        if flat:
            download_buttons(pd.DataFrame(flat), "jurnal_umum", "jurnal")
        for j in journals:
            with st.expander(f"{j['no']} · {j['date']} · {j['desc']} · {rupiah(j['total'])}"):
                st.dataframe(pd.DataFrame(j["items"], columns=["Kode", "Akun", "Debit", "Kredit"]),
                             width="stretch", hide_index=True, column_config=money_cfg("Debit", "Kredit"))

    with t_new:
        _manual_journal(coa_labels)

    with t_coa:
        st.dataframe(coa_df, width="stretch", hide_index=True)
        left, right = st.columns(2)
        with left:
            with st.form("form_coa_new", clear_on_submit=True):
                st.markdown("**Akun baru**")
                code = st.text_input("Kode")
                name = st.text_input("Nama akun")
                cat = st.selectbox("Kategori", ops.COA_CATEGORIES)
                nb = st.selectbox("Saldo normal", ["DEBIT", "KREDIT"])
                desc = st.text_input("Keterangan")
                if st.form_submit_button("Tambah akun"):
                    run_action(ops.create_coa, code, name, cat, nb, desc, ok="Akun ditambahkan.")
        with right:
            with st.form("form_coa_edit"):
                st.markdown("**Ubah akun**")
                code = st.selectbox("Pilih akun", list(coa_labels), format_func=coa_labels.get, key="coa_edit_pick")
                name = st.text_input("Nama baru (kosongkan bila tidak diubah)")
                desc = st.text_input("Keterangan baru (kosongkan bila tidak diubah)")
                if st.form_submit_button("Simpan perubahan"):
                    run_action(ops.update_coa, code, name or None, None, None, desc or None, ok="Akun diperbarui.")
