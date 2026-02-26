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
    """
    Extracts core identifier like 'Comp14_R-F_1' from long filenames.
    """
    match = re.search(r"(Comp\d+_[A-Z]-[A-Z]_\d+)", filename, re.IGNORECASE)
    return match.group(1) if match else re.sub(r"\.(log|out)$", "", filename, flags=re.IGNORECASE)

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v1.5", layout="wide")
st.title("SR-Boltzmann-Lab v1.5")
st.markdown(f"Enhanced Filename Matching for **{WAVELENGTH}**")

with st.sidebar:
    st.header("Computational Parameters")
    st.info(f"Method: ωB97X-D / def2-TZVP / SMD\n\nTemp: {TEMP} K\n\nR: {GAS_CONST}")

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Energy Data (Opt/Freq)")
    energy_files = st.file_uploader("Upload logs", accept_multiple_files=True, key="eng")
with col2:
    st.subheader("2. Specific Rotation Data (SR)")
    sr_files = st.file_uploader(f"Upload logs", accept_multiple_files=True, key="sr")

data_map = {}

# Process Energy Files
if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val is not None:
            base = get_base_name(f.name)
            data_map[base] = {"energy": val, "sr": None, "eng_name": f.name, "sr_name": None}

# Process SR Files
if sr_files:
    for f in sr_files:
        content = f.getvalue().decode("utf-8")
        val = extract_sr(content)
        if val is not None:
            base = get_base_name(f.name)
            if base in data_map:
                data_map[base]["sr"] = val
                data_map[base]["sr_name"] = f.name
            else:
                data_map[base] = {"energy": None, "sr": val, "eng_name": None, "sr_name": f.name}

ready_data = []
pending_data = []

for name, vals in data_map.items():
    if vals["energy"] is not None and vals["sr"] is not None:
        ready_data.append({"Conformer": name, "Energy (Ha)": vals["energy"], "SR Value": vals["sr"]})
    else:
        status = "Waiting for SR" if vals["sr"] is None else "Waiting for Energy"
        file_hint = vals["eng_name"] if vals["eng_name"] else vals["sr_name"]
        pending_data.append({"ID": name, "Status": status, "Source": file_hint})

st.write("---")
res_col, status_col = st.columns([2, 1])

with res_col:
    st.subheader("📊 Interim Average")
    if ready_data:
        df = pd.DataFrame(ready_data)
        min_e = df["Energy (Ha)"].min()
        df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
        df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                         df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
        df["Contribution"] = df["SR Value"] * (df["Pop (%)"] / 100)
        st.table(df[["Conformer", "ΔG (kcal/mol)", "Pop (%)", "SR Value", "Contribution"]])
        st.metric(label="Boltzmann Averaged [α]D", value=f"{df['Contribution'].sum():.2f} deg.")
    else:
        st.info("Drop files to start analysis.")

with status_col:
    st.subheader("⏳ Queue Status")
    if pending_data:
        st.dataframe(pd.DataFrame(pending_data), hide_index=True)
    else:
        st.success("All paired!")

st.download_button("Export CSV", pd.DataFrame(ready_data).to_csv(index=False) if ready_data else "", disabled=not ready_data)