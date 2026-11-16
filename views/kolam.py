import streamlit as st

from app.core.database import session_scope
from app.models.pond import Pond, StockMutation
from app.services import operations as ops
from views.common import rows_to_df, run_action


def render(user):
    st.header("Stok Kolam")
    with session_scope() as db:
        ponds = db.query(Pond).order_by(Pond.name).all()
        pond_names = {p.id: p.name for p in ponds}
        df = rows_to_df(ponds, {
            "name": "Kolam", "type": "Jenis", "dimension": "Dimensi", "status": "Status",
            "current_ekor": "Ekor", "capacity_ekor": "Kapasitas", "current_kg_estimasi": "Estimasi (kg)",
            "total_tebar": "Total tebar", "total_mati": "Total mati", "total_panen": "Total panen",
            "survival_rate": "Survival (%)",
        })
        muts = db.query(StockMutation).order_by(StockMutation.created_at.desc()).all()
        mut_rows = [{
            "Tanggal": m.date, "Kolam": pond_names.get(m.pond_id, "-"), "Jenis": m.type,
            "Ekor": m.ekor, "Berat (kg)": m.weight_kg, "Catatan": m.note, "Referensi": m.reference_id,
        } for m in muts]

    st.dataframe(df, width="stretch", hide_index=True)
    if not pond_names:
        st.info("Belum ada kolam. Tambahkan kolam pertama di tab 'Kolam baru'.")

    tab_tebar, tab_mati, tab_baru, tab_riwayat = st.tabs(
        ["Tebar bibit", "Catat mortalitas", "Kolam baru", "Riwayat mutasi"])

    with tab_tebar:
        with st.form("form_tebar", clear_on_submit=True):
            pid = st.selectbox("Kolam", list(pond_names), format_func=pond_names.get, key="tebar_pond")
            ekor = st.number_input("Jumlah ekor", min_value=0, step=100)
            kg = st.number_input("Total berat (kg)", min_value=0.0, step=1.0)
            note = st.text_input("Catatan", "Tebar bibit baru")
            if st.form_submit_button("Simpan tebar") and pid:
                run_action(ops.tebar_bibit, pid, ekor, kg, note, ok="Tebar bibit tercatat.")

    with tab_mati:
        with st.form("form_mati", clear_on_submit=True):
            pid = st.selectbox("Kolam", list(pond_names), format_func=pond_names.get, key="mati_pond")
            ekor = st.number_input("Ikan mati (ekor)", min_value=0, step=1)
            kg = st.number_input("Perkiraan berat (kg)", min_value=0.0, step=0.5)
            note = st.text_input("Catatan", "Kematian harian")
            if st.form_submit_button("Simpan mortalitas") and pid:
                run_action(ops.catat_mortalitas, pid, ekor, kg, note, ok="Mortalitas tercatat.")

    with tab_baru:
        with st.form("form_pond", clear_on_submit=True):
            name = st.text_input("Nama kolam")
            a, b = st.columns(2)
            type_ = a.selectbox("Jenis", ops.POND_TYPES)
            dim = b.text_input("Dimensi", placeholder="10m x 20m x 1.5m")
            cap = a.number_input("Kapasitas (ekor)", min_value=0, step=100)
            stock = b.number_input("Stok awal (ekor)", min_value=0, step=100)
            kg = a.number_input("Berat awal (kg)", min_value=0.0, step=1.0)
            if st.form_submit_button("Tambah kolam"):
                run_action(ops.create_pond, name, type_, dim, cap, stock, kg, ok="Kolam ditambahkan.")

    with tab_riwayat:
        st.dataframe(mut_rows, width="stretch", hide_index=True)
