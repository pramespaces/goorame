from datetime import date, timedelta

import streamlit as st

from app.core.database import session_scope
from app.models.pond import Pond
from app.models.sale import Sale
from app.services import operations as ops
from app.services.nota import build_nota_html
from views.common import cash_options, download_buttons, logo_b64, money_cfg, rows_to_df, run_action


def render(user):
    st.header("Penjualan & Piutang")
    with session_scope() as db:
        pond_names = {p.id: p.name for p in db.query(Pond).order_by(Pond.name).all()}
        cash = cash_options(db)
        sales = db.query(Sale).order_by(Sale.created_at.desc()).all()
        df = rows_to_df(sales, {
            "invoice_no": "No. Faktur", "date": "Tanggal", "buyer_name": "Pembeli",
            "quantity_ekor": "Ekor", "weight_kg": "Berat (kg)", "price_per_kg": "Harga/kg",
            "total_amount": "Total", "payment_status": "Status", "due_date": "Jatuh tempo",
            "cash_account_name": "Dompet",
        })
        tempo = {s.id: f"{s.invoice_no} — {s.buyer_name} (Rp {s.total_amount:,.0f})"
                 for s in sales if s.payment_status == "TEMPO"}
        all_sales = {s.id: f"{s.invoice_no} — {s.buyer_name} ({s.date})" for s in sales}

    tab_new, tab_pay, tab_list, tab_nota = st.tabs(
        ["Penjualan baru", "Pelunasan piutang", "Daftar penjualan", "Nota"])

    with tab_new:
        status = st.radio("Pembayaran", ["LUNAS", "TEMPO"], horizontal=True,
                          format_func=lambda s: "Tunai (lunas)" if s == "LUNAS" else "Tempo (piutang)")
        with st.form("form_sale", clear_on_submit=True):
            buyer = st.text_input("Nama pembeli")
            pid = st.selectbox("Kolam asal panen (opsional)", [None, *pond_names],
                               format_func=lambda x: "— tanpa kolam —" if x is None else pond_names[x])
            a, b, c = st.columns(3)
            qty = a.number_input("Jumlah ekor", min_value=0, step=1)
            kg = b.number_input("Berat (kg)", min_value=0.0, step=1.0)
            price = c.number_input("Harga per kg (Rp)", min_value=0.0, step=1000.0)
            st.caption(f"Total: Rp {kg * price:,.0f}")
            cash_id, due = None, None
            if status == "LUNAS":
                cash_id = st.selectbox("Masuk ke dompet", list(cash), format_func=cash.get)
            else:
                due = st.date_input("Jatuh tempo", date.today() + timedelta(days=14)).isoformat()
            note = st.text_input("Catatan")
            if st.form_submit_button("Simpan penjualan"):
                run_action(ops.create_sale, buyer, pid, qty, kg, price, status, cash_id, due, note,
                           ok="Penjualan tercatat dan jurnal dibuat otomatis.")

    with tab_pay:
        if not tempo:
            st.info("Tidak ada piutang yang belum lunas.")
        else:
            with st.form("form_pay_recv", clear_on_submit=True):
                sid = st.selectbox("Faktur tempo", list(tempo), format_func=tempo.get)
                cid = st.selectbox("Diterima di dompet", list(cash), format_func=cash.get)
                if st.form_submit_button("Catat pelunasan"):
                    run_action(ops.pay_receivable, sid, cid, ok="Piutang dilunasi.")

    with tab_list:
        st.dataframe(df, width="stretch", hide_index=True,
                     column_config=money_cfg("Harga/kg", "Total"))
        download_buttons(df, "penjualan", "penjualan")

    with tab_nota:
        if not all_sales:
            st.info("Belum ada penjualan.")
        else:
            sid = st.selectbox("Pilih faktur", list(all_sales), format_func=all_sales.get, key="nota_pick")
            with session_scope() as db:
                sale = db.query(Sale).filter(Sale.id == sid).first()
                html = build_nota_html(sale, logo_b64()) if sale else ""
                name = sale.invoice_no if sale else "nota"
            st.download_button("Unduh nota (HTML, siap cetak)", html, f"nota_{name}.html", "text/html")
            st.caption("Buka file hasil unduhan di browser, lalu klik Cetak / Simpan PDF.")
            with st.expander("Pratinjau nota", expanded=True):
                # semua isian pengguna di-escape di build_nota_html, aman untuk iframe
                if hasattr(st, "iframe"):
                    st.iframe(html, height=520)
                else:  # Streamlit versi lama
                    st.components.v1.html(html, height=520, scrolling=True)
