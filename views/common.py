"""Helper bersama untuk semua halaman Streamlit."""
import pandas as pd
import streamlit as st

from app.core.database import session_scope


def rupiah(value) -> str:
    try:
        return "Rp " + f"{float(value):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "Rp 0"


def flash(message: str, kind: str = "success"):
    st.session_state["_flash"] = (kind, message)


def show_flash():
    item = st.session_state.pop("_flash", None)
    if item:
        kind, message = item
        {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(message)


def run_action(func, *args, ok="Berhasil disimpan.", **kwargs) -> bool:
    """Jalankan operasi bisnis dalam satu sesi DB. Tampilkan error validasi
    bila gagal; bila sukses simpan pesan lalu muat ulang halaman."""
    try:
        with session_scope() as db:
            func(db, *args, **kwargs)
    except ValueError as exc:
        st.error(str(exc))
        return False
    except Exception as exc:  # error tak terduga (DB dsb.)
        st.error(f"Terjadi kesalahan: {exc}")
        return False
    flash(ok)
    st.rerun()
    return True


def rows_to_df(rows, columns: dict) -> pd.DataFrame:
    """columns = {atribut: judul kolom}"""
    data = [{title: getattr(r, attr) for attr, title in columns.items()} for r in rows]
    return pd.DataFrame(data, columns=list(columns.values()))


def money_cfg(*names):
    return {n: st.column_config.NumberColumn(n, format="Rp %d") for n in names}


def cash_options(db):
    from app.models.accounting import CashAccount
    accs = db.query(CashAccount).order_by(CashAccount.code).all()
    return {a.id: f"{a.name} — {rupiah(a.balance)}" for a in accs}


# ------------------------------------------------------------ periode, ekspor, aset
import base64
import io
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
PERIODS = ["Bulan ini", "Bulan lalu", "Tahun ini", "Semua periode", "Rentang kustom"]


def period_picker(key: str, default: str = "Bulan ini"):
    """Pemilih periode. Mengembalikan (start, end) berformat YYYY-MM-DD ('' = tanpa batas)."""
    c1, c2 = st.columns([1, 2])
    choice = c1.selectbox("Periode", PERIODS, index=PERIODS.index(default), key=f"{key}_period")
    today = date.today()
    if choice == "Bulan ini":
        start, end = today.replace(day=1), today.replace(day=monthrange(today.year, today.month)[1])
    elif choice == "Bulan lalu":
        last = today.replace(day=1) - timedelta(days=1)
        start, end = last.replace(day=1), last
    elif choice == "Tahun ini":
        start, end = date(today.year, 1, 1), date(today.year, 12, 31)
    elif choice == "Rentang kustom":
        rng = c2.date_input("Rentang tanggal", (today.replace(day=1), today), key=f"{key}_range")
        if isinstance(rng, (tuple, list)) and len(rng) == 2:
            start, end = rng
        else:
            c2.info("Pilih tanggal awal dan akhir.")
            st.stop()
    else:
        return "", ""
    c2.caption(f"{start.strftime('%d %b %Y')} s.d. {end.strftime('%d %b %Y')}")
    return start.isoformat(), end.isoformat()


def period_label(start: str, end: str) -> str:
    if not start and not end:
        return "Seluruh periode"
    return f"{start or 'awal'} s.d. {end or 'sekarang'}"


def to_excel(sheets: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            for col in ws.columns:
                width = max(len(str(c.value)) if c.value is not None else 0 for c in col) + 2
                ws.column_dimensions[col[0].column_letter].width = min(width, 48)
    return buf.getvalue()


def to_csv(df: pd.DataFrame) -> bytes:
    """CSV pemisah titik koma + BOM, supaya terbuka benar di Excel Indonesia."""
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def download_buttons(df_or_sheets, base_name: str, key: str):
    """Tombol unduh Excel dan CSV. Terima satu DataFrame atau dict {sheet: DataFrame}."""
    sheets = df_or_sheets if isinstance(df_or_sheets, dict) else {"Data": df_or_sheets}
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button("Unduh Excel", to_excel(sheets), f"{base_name}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"{key}_xlsx")
    first = next(iter(sheets.values()))
    c2.download_button("Unduh CSV", to_csv(first), f"{base_name}.csv", "text/csv", key=f"{key}_csv")


def logo_b64(name: str = "logo.png") -> str:
    return base64.b64encode((ASSETS / name).read_bytes()).decode()


def inject_css():
    st.markdown("""
<style>
html, body, [class*="css"] { font-family: "Segoe UI", system-ui, sans-serif; }
[data-testid="stSidebar"] { border-right: 3px solid #E9B949; }
[data-testid="stMetric"] {
  background: #FFFFFF; border: 1px solid #E5DFC8; border-left: 5px solid #1F6F54;
  border-radius: 10px; padding: 12px 16px; box-shadow: 0 1px 3px rgba(0,0,0,.06);
}
[data-testid="stMetricLabel"] p { color: #5b6b63; font-size: .85rem; }
h1, h2, h3 { color: #14513B; }
.stTabs [data-baseweb="tab-list"] { gap: 4px; }
.stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0 0; padding: 8px 14px; }
.stTabs [aria-selected="true"] { background: #F4F1E6; border-bottom: 3px solid #E9B949; }
div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {
  background: #1F6F54; border: 0; }
.goorame-footer { color:#8a948e; font-size:.78rem; text-align:center; margin-top:2rem; }
.login-title { text-align:center; color:#14513B; margin:0; }
.login-sub { text-align:center; color:#6b7a72; margin-bottom:1rem; }
</style>""", unsafe_allow_html=True)
