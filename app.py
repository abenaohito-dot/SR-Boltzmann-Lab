import streamlit as st
import pandas as pd
import re
import math

# ==========================================
# FIXED PHYSICAL CONSTANTS
# ==========================================
TEMP = 298.15              # 25.0 °C
GAS_CONST = 0.001987204    # kcal/(mol·K)
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
    match = re.search(r"(Comp\d+_[A-Z]-[A-Z]_\d+)", filename, re.IGNORECASE)
    return match.group(1) if match else re.sub(r"\.(log|out)$", "", filename, flags=re.IGNORECASE)

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v1.7", layout="wide")
st.title("SR-Boltzmann-Lab v1.7")
st.markdown(f"Running Analysis for **{WAVELENGTH}**")

with st.sidebar:
    st.header("Parameters")
    st.info(f"Method: ωB97X-D/def2-TZVP/SMD\n\nTemp: {TEMP} K\n\nR: {GAS_CONST}")

# Dual File Uploaders
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Energy Data")
    energy_files = st.file_uploader("Upload Opt/Freq logs", accept_multiple_files=True, key="eng")
with col2:
    st.subheader("2. SR Data")
    sr_files = st.file_uploader(f"Upload SR logs ({WAVELENGTH})", accept_multiple_files=True, key="sr")

# --- Processing Logic ---
data_map = {}
if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val:
            base = get_base_name(f.name)
            data_map[base] = {"energy": val, "sr": None, "eng_name": f.name, "sr_name": None}

if sr_files:
    for f in sr_files:
        base = get_base_name(f.name)
        content = f.getvalue().decode("utf-8")
        val = extract_sr(content)
        if val:
            if base not in data_map:
                data_map[base] = {"energy": None, "sr": val, "eng_name": None, "sr_name": f.name}
            else:
                data_map[base]["sr"] = val
                data_map[base]["sr_name"] = f.name

ready_data = []
pending_data = []
for name, v in data_map.items():
    if v["energy"] is not None and v["sr"] is not None:
        ready_data.append({"Conformer": name, "Energy (Ha)": v["energy"], "SR Value": v["sr"]})
    else:
        status = "Waiting for SR" if v["sr"] is None else "Waiting for Energy"
        pending_data.append({"ID": name, "Status": status})

# --- Display Window ---
st.write("---")
res_col, status_col = st.columns([2, 1])

is_ready = len(ready_data) > 0
final_sr = 0.0
csv_buffer = ""

with res_col:
    st.subheader("📊 Interim Average")
    if is_ready:
        df = pd.DataFrame(ready_data)
        min_e = df["Energy (Ha)"].min()
        df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
        df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                         df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
        df["Contribution"] = df["SR Value"] * (df["Pop (%)"] / 100)
        final_sr = df["Contribution"].sum()
        
        st.table(df[["Conformer", "ΔG (kcal/mol)", "Pop (%)", "SR Value", "Contribution"]])
        st.metric(label=f"Current Boltzmann Average [α]D", value=f"{final_sr:.2f} deg.")
        
        # Prepare CSV with Summary Row
        csv_df = df.copy()
        summary = pd.DataFrame([{"Conformer": "TOTAL / AVERAGE", "SR Value": final_sr}], index=[len(df)])
        csv_buffer = pd.concat([csv_df, summary]).to_csv(index=False)
    else:
        st.info("Awaiting paired log files...")

with status_col:
    st.subheader("⏳ Queue Status")
    if pending_data:
        st.dataframe(pd.DataFrame(pending_data), hide_index=True)
    else:
        st.success("All conformers paired!")

# Final Action
st.download_button(
    label="Download SI-Data (CSV)",
    data=csv_buffer,
    file_name=f"SR_Results_{final_sr:.1f}.csv",
    disabled=not is_ready
)