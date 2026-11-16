import pandas as pd
import streamlit as st

from app.core.database import session_scope
from app.services.accounting_service import calculate_balance_sheet, calculate_income_statement, cash_flow
from views.common import download_buttons, money_cfg, period_label, period_picker, rupiah

COLS = {"code": "Kode", "name": "Akun", "amount": "Jumlah"}


def _frame(rows):
    return pd.DataFrame(rows, columns=list(COLS)).rename(columns=COLS)


def _laba_rugi(start, end):
    with session_scope() as db:
        inc = calculate_income_statement(db, start, end)
    st.caption(f"Laporan Laba Rugi · {period_label(start, end)}")
    rev, hpp, ops_ = _frame(inc["revenues"]), _frame(inc["hpp"]), _frame(inc["operating"])
    st.subheader("Pendapatan")
    st.dataframe(rev, width="stretch", hide_index=True, column_config=money_cfg("Jumlah"))
    st.subheader("Harga pokok penjualan (HPP)")
    st.dataframe(hpp, width="stretch", hide_index=True, column_config=money_cfg("Jumlah"))
    st.metric("Laba kotor", rupiah(inc["gross_profit"]))
    st.subheader("Beban operasional")
    st.dataframe(ops_, width="stretch", hide_index=True, column_config=money_cfg("Jumlah"))
    a, b, c, d = st.columns(4)
    a.metric("Total pendapatan", rupiah(inc["total_revenue"]))
    b.metric("HPP + beban", rupiah(inc["total_expense"]))
    c.metric("Laba bersih", rupiah(inc["net_income"]))
    d.metric("Margin laba", f"{inc['margin']:.1f}%")
    summary = pd.DataFrame([
        ("Total pendapatan", inc["total_revenue"]), ("Total HPP", inc["total_hpp"]),
        ("Laba kotor", inc["gross_profit"]), ("Total beban operasional", inc["total_operating"]),
        ("Laba bersih", inc["net_income"])], columns=["Ringkasan", "Jumlah"])
    download_buttons({"Ringkasan": summary, "Pendapatan": rev, "HPP": hpp, "Beban operasional": ops_},
                     "laba_rugi", "lr")


def _neraca(end):
    with session_scope() as db:
        bs = calculate_balance_sheet(db, end)
    st.caption(f"Neraca per {end or 'sekarang'}")
    assets, liab, eq = _frame(bs["assets"]), _frame(bs["liabilities"]), _frame(bs["equities"])
    eq_full = pd.concat([eq, pd.DataFrame([{"Kode": "", "Akun": "Laba berjalan", "Jumlah": bs["current_earnings"]}])],
                        ignore_index=True)
    left, right = st.columns(2)
    with left:
        st.subheader("Aset")
        st.dataframe(assets, width="stretch", hide_index=True, column_config=money_cfg("Jumlah"))
        st.metric("Total aset", rupiah(bs["total_assets"]))
    with right:
        st.subheader("Kewajiban")
        st.dataframe(liab, width="stretch", hide_index=True, column_config=money_cfg("Jumlah"))
        st.subheader("Ekuitas")
        st.dataframe(eq_full, width="stretch", hide_index=True, column_config=money_cfg("Jumlah"))
        st.metric("Kewajiban + ekuitas", rupiah(bs["total_liabilities"] + bs["total_equity"]))
    if bs["is_balanced"]:
        st.success("Neraca seimbang: aset = kewajiban + ekuitas.")
    else:
        st.warning("Neraca tidak seimbang: ada saldo awal yang belum dijurnal.")
    download_buttons({"Aset": assets, "Kewajiban": liab, "Ekuitas": eq_full}, "neraca", "nr")


def _arus_kas(start, end):
    with session_scope() as db:
        cf = cash_flow(db, start, end)
    st.caption(f"Arus kas berbasis jurnal pada akun kas & bank · {period_label(start, end)}")
    a, b, c, d = st.columns(4)
    a.metric("Kas awal", rupiah(cf["opening"]))
    b.metric("Kas masuk", rupiah(cf["total_in"]))
    c.metric("Kas keluar", rupiah(cf["total_out"]))
    d.metric("Kas akhir", rupiah(cf["closing"]))
    df = pd.DataFrame([{"Jenis transaksi": r["type"], "Masuk": r["cash_in"], "Keluar": r["cash_out"],
                        "Neto": r["net"]} for r in cf["rows"]], columns=["Jenis transaksi", "Masuk", "Keluar", "Neto"])
    st.dataframe(df, width="stretch", hide_index=True, column_config=money_cfg("Masuk", "Keluar", "Neto"))
    st.caption("Transfer antar rekening muncul di kas masuk dan keluar dengan nilai sama (neto nol).")
    acc = pd.DataFrame([{"Kode": r["code"], "Rekening": r["name"], "Saldo menurut jurnal": r["journal_balance"],
                         "Saldo tercatat": r["recorded_balance"],
                         "Selisih": r["recorded_balance"] - r["journal_balance"]} for r in cf["per_account"]])
    with st.expander("Rekonsiliasi saldo rekening (jurnal vs tercatat)"):
        st.dataframe(acc, width="stretch", hide_index=True,
                     column_config=money_cfg("Saldo menurut jurnal", "Saldo tercatat", "Selisih"))
        if not acc.empty and (acc["Selisih"].abs() > 0.5).any():
            st.warning("Ada selisih: saldo rekening berbeda dari hasil jurnal (mis. saldo awal belum dijurnal).")
        else:
            st.success("Saldo rekening sesuai dengan jurnal.")
    download_buttons({"Arus kas": df, "Rekonsiliasi": acc}, "arus_kas", "ak")


def render(user):
    st.header("Laporan Keuangan")
    start, end = period_picker("lap")
    t1, t2, t3 = st.tabs(["Laba rugi", "Neraca", "Arus kas"])
    with t1:
        _laba_rugi(start, end)
    with t2:
        _neraca(end)
    with t3:
        _arus_kas(start, end)
