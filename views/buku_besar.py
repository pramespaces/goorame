import pandas as pd
import streamlit as st

from app.core.database import session_scope
from app.models.accounting import ChartOfAccount
from app.services.accounting_service import account_ledger, calculate_general_ledger, trial_balance
from views.common import download_buttons, money_cfg, period_label, period_picker, rupiah


def _per_akun(start, end):
    with session_scope() as db:
        coas = db.query(ChartOfAccount).order_by(ChartOfAccount.code).all()
        options = {c.code: f"{c.code} — {c.name}" for c in coas}
    if not options:
        st.info("Bagan akun masih kosong.")
        return
    code = st.selectbox("Akun", list(options), format_func=options.get, key="bb_akun")
    with session_scope() as db:
        led = account_ledger(db, code, start, end)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Saldo awal", rupiah(led["opening"]))
    m2.metric("Total debit", rupiah(led["total_debit"]))
    m3.metric("Total kredit", rupiah(led["total_credit"]))
    m4.metric("Saldo akhir", rupiah(led["ending"]))
    st.caption(f"{led['name']} · kategori {led['category']} · saldo normal {led['normal_balance']} · "
               f"{period_label(start, end)}")

    rows = [{"Tanggal": "", "No. Jurnal": "", "Keterangan": "Saldo awal", "Debit": None, "Kredit": None,
             "Saldo": led["opening"]}]
    rows += [{"Tanggal": r["date"], "No. Jurnal": r["entry_number"], "Keterangan": r["description"],
              "Debit": r["debit"] or None, "Kredit": r["credit"] or None, "Saldo": r["balance"]}
             for r in led["rows"]]
    df = pd.DataFrame(rows)
    if len(df) == 1:
        st.info("Belum ada mutasi pada periode ini.")
    st.dataframe(df, width="stretch", hide_index=True, column_config=money_cfg("Debit", "Kredit", "Saldo"))
    download_buttons(df, f"buku_besar_{code}", f"bb_{code}")


def _ringkasan(start, end):
    with session_scope() as db:
        gl = calculate_general_ledger(db, start, end)
    df = pd.DataFrame(gl).rename(columns={
        "code": "Kode", "name": "Akun", "category": "Kategori", "normal_balance": "Saldo normal",
        "opening_balance": "Saldo awal", "total_debit": "Debit", "total_credit": "Kredit",
        "ending_balance": "Saldo akhir", "transaction_count": "Transaksi"})
    df = df[["Kode", "Akun", "Kategori", "Saldo normal", "Saldo awal", "Debit", "Kredit", "Saldo akhir", "Transaksi"]]
    only_active = st.checkbox("Sembunyikan akun tanpa saldo/mutasi", value=True, key="bb_active")
    if only_active:
        df = df[(df["Saldo awal"] != 0) | (df["Debit"] != 0) | (df["Kredit"] != 0) | (df["Saldo akhir"] != 0)]
    cats = st.multiselect("Kategori", sorted(df["Kategori"].unique()), key="bb_cats")
    if cats:
        df = df[df["Kategori"].isin(cats)]
    st.dataframe(df, width="stretch", hide_index=True,
                 column_config=money_cfg("Saldo awal", "Debit", "Kredit", "Saldo akhir"))
    st.caption(f"Total debit {rupiah(df['Debit'].sum())} · total kredit {rupiah(df['Kredit'].sum())} "
               f"· {period_label(start, end)}")
    download_buttons(df, "buku_besar_ringkasan", "bb_sum")


def _neraca_saldo(end):
    with session_scope() as db:
        tb = trial_balance(db, end)
    df = pd.DataFrame(tb["rows"]).rename(columns={"code": "Kode", "name": "Akun", "category": "Kategori",
                                                  "debit": "Debit", "credit": "Kredit"})
    df = df[(df["Debit"] != 0) | (df["Kredit"] != 0)][["Kode", "Akun", "Kategori", "Debit", "Kredit"]]
    st.dataframe(df, width="stretch", hide_index=True, column_config=money_cfg("Debit", "Kredit"))
    a, b = st.columns(2)
    a.metric("Total debit", rupiah(tb["total_debit"]))
    b.metric("Total kredit", rupiah(tb["total_credit"]))
    (st.success if tb["balanced"] else st.error)(
        "Neraca saldo seimbang." if tb["balanced"] else "Neraca saldo TIDAK seimbang.")
    download_buttons(df, "neraca_saldo", "ns")


def render(user):
    st.header("Buku Besar")
    st.caption("Mutasi per akun dengan saldo berjalan, ringkasan semua akun, dan neraca saldo.")
    start, end = period_picker("bb")
    t1, t2, t3 = st.tabs(["Per akun", "Ringkasan semua akun", "Neraca saldo"])
    with t1:
        _per_akun(start, end)
    with t2:
        _ringkasan(start, end)
    with t3:
        st.caption(f"Neraca saldo per tanggal: {end or 'sekarang'}")
        _neraca_saldo(end)
