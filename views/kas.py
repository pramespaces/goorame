import pandas as pd
import streamlit as st

from app.core.database import session_scope
from app.models.accounting import CashAccount, JournalEntry, JournalItem
from app.services import operations as ops
from views.common import cash_options, money_cfg, rows_to_df, run_action, rupiah


def render(user):
    st.header("Kas & Bank")
    with session_scope() as db:
        accs = db.query(CashAccount).order_by(CashAccount.code).all()
        acc_df = rows_to_df(accs, {"code": "Kode", "name": "Rekening", "type": "Jenis",
                                   "account_number": "No. Rekening", "balance": "Saldo"})
        options = {a.code: a.name for a in accs}
        cash = cash_options(db)

    st.metric("Total kas & bank", rupiah(acc_df["Saldo"].sum()))
    st.dataframe(acc_df, width="stretch", hide_index=True, column_config=money_cfg("Saldo"))

    t_book, t_trf, t_new = st.tabs(["Buku kas", "Transfer antar rekening", "Rekening baru"])
    with t_book:
        if options:
            code = st.selectbox("Rekening", list(options), format_func=lambda c: f"{c} — {options[c]}")
            with session_scope() as db:
                rows = (db.query(JournalItem, JournalEntry).join(JournalEntry)
                        .filter(JournalItem.account_code == code)
                        .order_by(JournalEntry.date, JournalEntry.created_at).all())
                data = [{"Tanggal": e.date, "No. Jurnal": e.entry_number, "Keterangan": e.description,
                         "Masuk": i.debit, "Keluar": i.credit} for i, e in rows]
            book = pd.DataFrame(data, columns=["Tanggal", "No. Jurnal", "Keterangan", "Masuk", "Keluar"])
            book["Saldo berjalan"] = (book["Masuk"] - book["Keluar"]).cumsum()
            st.dataframe(book, width="stretch", hide_index=True,
                         column_config=money_cfg("Masuk", "Keluar", "Saldo berjalan"))
            st.caption("Saldo berjalan dihitung dari jurnal; saldo awal rekening tidak ikut jika dicatat tanpa jurnal.")
    with t_trf:
        with st.form("form_transfer", clear_on_submit=True):
            src = st.selectbox("Dari", list(cash), format_func=cash.get, key="trf_from")
            dst = st.selectbox("Ke", list(cash), format_func=cash.get, key="trf_to")
            amount = st.number_input("Nominal (Rp)", min_value=0.0, step=100000.0)
            note = st.text_input("Catatan")
            if st.form_submit_button("Transfer"):
                run_action(ops.transfer_cash, src, dst, amount, note, ok="Transfer berhasil dan jurnal dibuat.")
    with t_new:
        with st.form("form_cash_acc", clear_on_submit=True):
            name = st.text_input("Nama rekening")
            a, b = st.columns(2)
            type_ = a.selectbox("Jenis", ["BANK", "KAS"])
            number = b.text_input("No. rekening")
            bal = st.number_input("Saldo awal (Rp)", min_value=0.0, step=100000.0)
            if st.form_submit_button("Tambah rekening"):
                run_action(ops.create_cash_account, name, type_, number, bal, ok="Rekening ditambahkan.")
