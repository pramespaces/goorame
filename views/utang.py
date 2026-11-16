from datetime import date, timedelta

import streamlit as st

from app.core.database import session_scope
from app.models.expense import SupplierInvoice
from app.models.sale import Sale
from app.services import operations as ops
from views.common import cash_options, money_cfg, rows_to_df, run_action, rupiah

CATEGORIES = ["Pakan", "Bibit", "Obat / Suplemen", "Operasional"]


def render(user):
    st.header("Utang Pemasok & Piutang")
    with session_scope() as db:
        cash = cash_options(db)
        invs = db.query(SupplierInvoice).order_by(SupplierInvoice.created_at.desc()).all()
        inv_df = rows_to_df(invs, {
            "invoice_number": "No. Faktur", "date": "Tanggal", "supplier_name": "Supplier",
            "item_category": "Kategori", "total_amount": "Total", "paid_amount": "Dibayar",
            "due_date": "Jatuh tempo", "status": "Status",
        })
        inv_df["Sisa"] = inv_df["Total"] - inv_df["Dibayar"]
        open_invs = {i.id: f"{i.invoice_number} — {i.supplier_name} (sisa {rupiah(i.total_amount - i.paid_amount)})"
                     for i in invs if i.status != "LUNAS"}
        tempo = db.query(Sale).filter(Sale.payment_status == "TEMPO").order_by(Sale.due_date).all()
        rec_df = rows_to_df(tempo, {"invoice_no": "No. Faktur", "date": "Tanggal", "buyer_name": "Pembeli",
                                    "total_amount": "Total", "due_date": "Jatuh tempo"})
    m1, m2 = st.columns(2)
    m1.metric("Total utang pemasok", rupiah(inv_df.loc[inv_df["Status"] != "LUNAS", "Sisa"].sum()))
    m2.metric("Total piutang pelanggan", rupiah(rec_df["Total"].sum()))

    t_inv, t_new, t_pay, t_rec = st.tabs(["Faktur supplier", "Faktur baru", "Bayar utang", "Kartu piutang"])
    with t_inv:
        st.dataframe(inv_df, width="stretch", hide_index=True,
                     column_config=money_cfg("Total", "Dibayar", "Sisa"))
    with t_new:
        with st.form("form_inv", clear_on_submit=True):
            sup = st.text_input("Nama supplier")
            a, b = st.columns(2)
            cat = a.selectbox("Kategori", CATEGORIES)
            total = b.number_input("Total tagihan (Rp)", min_value=0.0, step=100000.0)
            due = st.date_input("Jatuh tempo", date.today() + timedelta(days=30)).isoformat()
            note = st.text_input("Catatan")
            if st.form_submit_button("Simpan faktur"):
                run_action(ops.create_supplier_invoice, sup, cat, total, due, note,
                           ok="Faktur supplier tercatat dan jurnal utang dibuat.")
    with t_pay:
        if not open_invs:
            st.info("Tidak ada utang yang belum lunas.")
        else:
            with st.form("form_pay_inv", clear_on_submit=True):
                iid = st.selectbox("Faktur", list(open_invs), format_func=open_invs.get)
                amt = st.number_input("Jumlah dibayar (Rp)", min_value=0.0, step=100000.0)
                cid = st.selectbox("Dibayar dari", list(cash), format_func=cash.get)
                note = st.text_input("Catatan")
                if st.form_submit_button("Bayar"):
                    run_action(ops.pay_supplier_invoice, iid, amt, cid, note, ok="Pembayaran utang tercatat.")
    with t_rec:
        st.caption("Pelunasan piutang dilakukan di menu Penjualan → Pelunasan piutang.")
        st.dataframe(rec_df, width="stretch", hide_index=True, column_config=money_cfg("Total"))
