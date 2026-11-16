import pandas as pd
import streamlit as st

from app.core.database import session_scope
from app.models.accounting import CashAccount, JournalEntry
from app.models.pond import Pond
from app.services.accounting_service import monthly_series
from app.services.operations import dashboard_summary, get_alerts
from views.common import rupiah


def render(user):
    st.header("Dashboard")
    owner = user["role"] == "PEMILIK"
    with session_scope() as db:
        ponds = db.query(Pond).order_by(Pond.name).all()
        pond_rows = [{
            "Kolam": p.name, "Jenis": p.type, "Status": p.status, "Ekor": p.current_ekor,
            "Kapasitas": p.capacity_ekor,
            "Terisi (%)": round(p.current_ekor / p.capacity_ekor * 100, 1) if p.capacity_ekor else 0.0,
            "Estimasi (kg)": p.current_kg_estimasi, "Survival (%)": p.survival_rate,
        } for p in ponds]
        s = dashboard_summary(db)
        alerts = get_alerts(db) if owner else []
        cash = [(c.name, c.balance) for c in db.query(CashAccount).order_by(CashAccount.code).all()]
        series = monthly_series(db, 6) if owner else []
        recent = db.query(JournalEntry).order_by(JournalEntry.created_at.desc()).limit(8).all()
        recent_rows = [{"No": j.entry_number, "Tanggal": j.date, "Keterangan": j.description, "Tipe": j.ref_type}
                       for j in recent]

    if owner and alerts:
        with st.expander(f"Peringatan ({len(alerts)})", expanded=any(k == "error" for k, _ in alerts)):
            for kind, msg in alerts:
                (st.error if kind == "error" else st.warning)(msg, icon="🚨" if kind == "error" else "⚠️")

    st.subheader("Operasional budidaya")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ikan di kolam", f"{s['total_fish_count']:,} ekor".replace(",", "."))
    c2.metric("Estimasi bobot", f"{s['total_fish_weight']:,.1f} kg")
    c3.metric("Jumlah kolam", s["pond_count"])
    fill = s["total_fish_count"] / s["total_capacity"] * 100 if s["total_capacity"] else 0
    c4.metric("Keterisian kolam", f"{fill:.0f}%")

    if owner:
        st.subheader("Keuangan")
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Total kas & bank", rupiah(s["total_cash"]))
        a2.metric("Piutang (tempo)", rupiah(s["total_receivable_due"]))
        a3.metric("Utang pemasok", rupiah(s["total_payable_due"]))
        a4.metric("Laba bersih (total)", rupiah(s["net_income"]))
        b1, b2, b3 = st.columns(3)
        b1.metric("Pendapatan bulan ini", rupiah(s["month_revenue"]))
        b2.metric("Beban bulan ini", rupiah(s["month_expense"]))
        b3.metric("Laba bulan ini", rupiah(s["month_net"]))

        left, right = st.columns([3, 2])
        with left:
            st.markdown("**Pendapatan vs beban, 6 bulan terakhir**")
            df = pd.DataFrame(series).set_index("Bulan")[["Pendapatan", "Beban"]]
            st.bar_chart(df, color=["#1F6F54", "#E9B949"])
        with right:
            st.markdown("**Saldo per rekening**")
            st.bar_chart(pd.DataFrame(cash, columns=["Rekening", "Saldo"]).set_index("Rekening"),
                         color="#1F6F54", horizontal=True)

    st.subheader("Status kolam")
    st.dataframe(
        pd.DataFrame(pond_rows), width="stretch", hide_index=True,
        column_config={
            "Terisi (%)": st.column_config.ProgressColumn("Terisi (%)", min_value=0, max_value=100, format="%.0f"),
            "Survival (%)": st.column_config.ProgressColumn("Survival (%)", min_value=0, max_value=100, format="%.1f"),
        })
    if owner:
        st.subheader("Jurnal terbaru")
        st.dataframe(pd.DataFrame(recent_rows), width="stretch", hide_index=True)
