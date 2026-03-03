import streamlit as st
import pandas as pd
import re
import math
import matplotlib.pyplot as plt
import plotly.express as px
import io

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
    # 1. 5983.0 A などの波長指定がある [Alpha] を最優先（GL/GV問わず波長一致を重視）
    match = re.search(r"\[Alpha\]\s+\(\s*[\d\.]+\s+A\)\s+=\s+(-?\d+\.\d+)", content)
    if match:
        return float(match.group(1))
    
    # 2. 波長指定がない場合、GL (GIAO) の static を探す
    match = re.search(r"Optical Rotation GL:.*?\[Alpha\]D\s+\(static\)\s+=\s+(-?\d+\.\d+)", content, re.DOTALL)
    if match:
        return float(match.group(1))

    # 3. 汎用的な [Alpha] 検索
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_id(filename):
    name = filename.lower().replace(".log", "").replace(".out", "")
    match = re.search(r"(\d+)$", name)
    if match:
        return match.group(1)
    return name

# --- UI ---
st.set_page_config(page_title="SR-Boltzmann-Lab v2.6.1", layout="wide")
st.title("SR-Boltzmann-Lab v2.6.1")

# Sidebar
with st.sidebar:
    st.header("1. Experimental Reference")
    exp_val = st.number_input("Experimental [α]D (deg.)", value=0.0, step=0.1)
    st.divider()
    st.header("2. Settings")
    st.info(f"Target: {WAVELENGTH}\nTemp: {TEMP} K")

# Uploaders
col1, col2 = st.columns(2)
with col1:
    energy_files = st.file_uploader("Opt/Freq logs", accept_multiple_files=True, key="eng")
with col2:
    sr_files = st.file_uploader("TD-DFT logs", accept_multiple_files=True, key="sr")

# Processing
data_map = {}
if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val: data_map[get_base_id(f.name)] = {"name": f.name, "energy": val, "sr": None}

if sr_files:
    for f in sr_files:
        file_id = get_base_id(f.name)
        content = f.getvalue().decode("utf-8")
        val = extract_sr(content)
        if val:
            if file_id in data_map: data_map[file_id]["sr"] = val
            else: data_map[file_id] = {"name": f.name, "energy": None, "sr": val}

ready_data = []
for file_id, v in data_map.items():
    if v["energy"] is not None and v["sr"] is not None:
        ready_data.append({"ID": file_id, "File": v["name"], "Energy (Ha)": v["energy"], "Raw SR": v["sr"]})

# Results
if ready_data:
    df = pd.DataFrame(ready_data)
    min_e = df["Energy (Ha)"].min()
    df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
    df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                     df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
    df["Contribution"] = df["Raw SR"] * (df["Pop (%)"] / 100)
    final_sr = df["Contribution"].sum()

    res_col, plot_col = st.columns([2, 3])
    with res_col:
        st.subheader("📊 Summary")
        st.table(df[["ID", "ΔG (kcal/mol)", "Pop (%)", "Raw SR", "Contribution"]])
        st.metric("Boltzmann Averaged [α]D", f"{final_sr:.2f} deg.")

    with plot_col:
        fig_px = px.scatter(df, x="ΔG (kcal/mol)", y="Raw SR", size="Pop (%)", color="Pop (%)",
                            hover_name="ID", template="plotly_white")
        fig_px.add_hline(y=final_sr, line_dash="dash", line_color="red")
        st.plotly_chart(fig_px, use_container_width=True)

    csv_buffer = df.to_csv(index=False)
    st.download_button("Download CSV", data=csv_buffer, file_name="results.csv")
else:
    st.info("Waiting for logs...")