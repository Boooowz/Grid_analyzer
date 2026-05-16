"""Streamlit UI για το Grid Analyzer."""
from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from analyzer import analyze

st.set_page_config(
    page_title="Grid Analyzer",
    page_icon="📊",
    layout="wide",
)

st.title("Grid Analyzer")
st.caption(
    "Ανέβασε το μηνιαίο αρχείο της Εργάνης (.xlsx) "
    "και δες ανά εργαζόμενο: μέρες εργασίας, νυχτερινές ώρες, "
    "ώρες Κυριακής, νυχτερινές ώρες Κυριακής και σύνολο Κυριακών."
)

uploaded = st.file_uploader("Επίλεξε αρχείο Excel", type=["xlsx", "xls"])

if not uploaded:
    st.info("Περιμένω αρχείο για ανάλυση...")
    st.stop()

try:
    raw = pd.read_excel(uploaded, header=0)
except Exception as exc:
    st.error(f"Δεν μπόρεσα να διαβάσω το αρχείο: {exc}")
    st.stop()

with st.spinner("Υπολογισμός..."):
    try:
        result = analyze(raw)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

if result.empty:
    st.warning("Δεν βρέθηκαν γραμμές εργασίας στο αρχείο.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Εργαζόμενοι", len(result))
c2.metric("Σύνολο Ωρών", f"{result['Σύνολο Ωρών'].sum():.1f}")
c3.metric("Νυχτερινές Ώρες", f"{result['Νυχτερινές Ώρες'].sum():.1f}")
c4.metric("Ώρες Κυριακής", f"{result['Ώρες Κυριακής'].sum():.1f}")

st.subheader("Ανάλυση ανά εργαζόμενο")
st.dataframe(result, use_container_width=True, hide_index=True)

st.subheader("Εξαγωγή")
col_csv, col_xlsx = st.columns(2)

csv_bytes = result.to_csv(index=False).encode("utf-8-sig")
col_csv.download_button(
    "Κατέβασε CSV",
    csv_bytes,
    file_name="analysis.csv",
    mime="text/csv",
    use_container_width=True,
)

xlsx_buf = io.BytesIO()
with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
    result.to_excel(writer, index=False, sheet_name="Ανάλυση")
col_xlsx.download_button(
    "Κατέβασε Excel",
    xlsx_buf.getvalue(),
    file_name="analysis.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    use_container_width=True,
)

with st.expander("Δες τα δεδομένα εισόδου (πρώτες 50 γραμμές)"):
    st.dataframe(raw.head(50), use_container_width=True)
