import streamlit as st

from app.core.database import session_scope
from app.models.expense import Expense
from app.services import operations as ops
from views.common import cash_options, money_cfg, rows_to_df, run_action, rupiah


def render(user):
    st.header("Pengeluaran")
    with session_scope() as db:
        cash = cash_options(db)
        expenses = db.query(Expense).order_by(Expense.created_at.desc()).all()
        df = rows_to_df(expenses, {
            "expense_no": "No.", "date": "Tanggal", "category": "Kategori", "nominal": "Nominal",
            "cash_account_name": "Dibayar dari", "note": "Catatan",
        })

    with st.form("form_expense", clear_on_submit=True):
        a, b = st.columns(2)
        cat = a.selectbox("Kategori", list(ops.EXPENSE_COA_MAP))
        nominal = b.number_input("Nominal (Rp)", min_value=0.0, step=10000.0)
        cid = st.selectbox("Dibayar dari", list(cash), format_func=cash.get)
        note = st.text_input("Catatan")
        if st.form_submit_button("Simpan pengeluaran"):
            run_action(ops.create_expense, cat, nominal, cid, note,
                       ok="Pengeluaran tercatat dan jurnal dibuat otomatis.")

    st.subheader("Riwayat")
    if df.empty:
        st.info("Belum ada pengeluaran.")
        return
    filt = st.multiselect("Filter kategori", sorted(df["Kategori"].unique()))
    view = df[df["Kategori"].isin(filt)] if filt else df
    st.metric("Total ditampilkan", rupiah(view["Nominal"].sum()))
    st.dataframe(view, width="stretch", hide_index=True, column_config=money_cfg("Nominal"))
