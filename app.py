import streamlit as st
import pandas as pd
import re
import math

# ==========================================
# FIXED PHYSICAL CONSTANTS
# ==========================================
TEMP = 298.15
GAS_CONST = 0.001987204
AU_TO_KCAL = 627.5095
WAVELENGTH = "589.3 nm"

def extract_energy(content):
    match = re.search(r"Sum of electronic and thermal Free Energies=\s+(-?\d+\.\d+)", content)
    if not match:
        match = re.search(r"SCF Done:.*?=\s+(-?\d+\.\d+)", content)
    return float(match.group(1)) if match else None

def extract_sr(content):
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_name(filename):
    return re.sub(r"(_tddft|_sr|_opt|_freq|_smd|_wb97)?\.(log|out)$", "", filename, flags=re.IGNORECASE)

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v1.4", layout="wide")
st.title("SR-Boltzmann-Lab v1.4")
st.markdown(f"Running Analysis for **{WAVELENGTH}**")

# Sidebar for transparency
with st.sidebar:
    st.header("Computational Parameters")
    st.info(f"Method: ωB97X-D / def2-TZVP / SMD\n\nTemp: {TEMP} K\n\nR: {GAS_CONST}")

# Dual File Uploaders
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Energy Data")
    energy_files = st.file_uploader("Upload logs", accept_multiple_files=True, key="eng")
with col2:
    st.subheader("2. SR Data")
    sr_files = st.file_uploader(f"Upload logs", accept_multiple_files=True, key="sr")

# --- Real-time Data processing ---
data_map = {}

if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val:
            base = get_base_name(f.name)
            data_map[base] = {"energy": val, "sr": None}

if sr_files:
    for f in sr_files:
        base = get_base_name(f.name)
        content = f.getvalue().decode("utf-8")
        val = extract_sr(content)
        if val:
            if base not in data_map:
                data_map[base] = {"energy": None, "sr": val}
            else:
                data_map[base]["sr"] = val

# Build status tracking
ready_data = []
pending_data = []

for name, vals in data_map.items():
    if vals["energy"] is not None and vals["sr"] is not None:
        ready_data.append({"Conformer": name, "Energy (Ha)": vals["energy"], "SR Value": vals["sr"]})
    else:
        status = "Waiting for SR" if vals["sr"] is None else "Waiting for Energy"
        pending_data.append({"Conformer": name, "Status": status})

# --- Analysis Window ---
st.write("---")
res_col, status_col = st.columns([2, 1])

with res_col:
    st.subheader("📊 Current Calculation (Running Average)")
    if ready_data:
        df = pd.DataFrame(ready_data)
        min_e = df["Energy (Ha)"].min()
        df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
        df["Factor"] = df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP)))
        df["Pop (%)"] = (df["Factor"] / df["Factor"].sum()) * 100
        df["Contribution"] = df["SR Value"] * (df["Pop (%)"] / 100)
        
        st.table(df[["Conformer", "ΔG (kcal/mol)", "Pop (%)", "SR Value", "Contribution"]])
        st.metric(label=f"Interim Average [α]D", value=f"{df['Contribution'].sum():.2f} deg.")
    else:
        st.info("No complete pairs found yet.")

with status_col:
    st.subheader("⏳ Queue Status")
    if pending_data:
        st.dataframe(pd.DataFrame(pending_data), hide_index=True)
    else:
        st.success("All conformers synced!")

# Download button (Always visible but disabled if no data)
st.download_button(
    label="Export Current Results (CSV)",
    data=pd.DataFrame(ready_data).to_csv(index=False) if ready_data else "",
    file_name="SR_In_Progress_Results.csv",
    disabled=not ready_data
)