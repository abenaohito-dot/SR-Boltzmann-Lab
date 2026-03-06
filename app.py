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
WAVELENGTH_LABEL = "589.3 nm (D-line)"

def extract_energy(content):
    match = re.search(r"Sum of electronic and thermal Free Energies=\s+(-?\d+\.\d+)", content)
    if not match:
        match = re.search(r"SCF Done:.*?=\s+(-?\d+\.\d+)", content)
    return float(match.group(1)) if match else None

def extract_sr(content):
    gl_section = re.search(r"Optical Rotation GL:.*?(?=\n\s*\n|Optical Rotation GL\*W|Optical Rotation|$)", content, re.DOTALL)
    if gl_section:
        section_text = gl_section.group(0)
        match = re.search(r"\[Alpha\]\s+\(\s*[\d\.]+\s+A\)\s+=\s+(-?\d+\.\d+)", section_text)
        if match: return float(match.group(1))
        match = re.search(r"\[Alpha\]D\s+\(static\)\s+=\s+(-?\d+\.\d+)", section_text)
        if match: return float(match.group(1))

    matches = re.findall(r"\[Alpha\]\s+\(\s*[\d\.]+\s+A\)\s+=\s+(-?\d+\.\d+)", content)
    if matches: return float(matches[-1])
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_id(filename):
    name = filename.lower().replace(".log", "").replace(".out", "")
    match = re.search(r"(\d+)$", name)
    return match.group(1) if match else name

# --- UI ---
st.set_page_config(page_title="SR-Boltzmann-Lab v2.6.4", layout="wide")
st.title("SR-Boltzmann-Lab v2.6.4 (Excel Optimized)")

with st.sidebar:
    st.header("1. Experimental Reference")
    exp_val = st.number_input("Exp. Alpha_D (deg.)", value=0.0, step=0.1)
    st.divider()
    st.header("2. Environment")
    st.info(f"Target: {WAVELENGTH_LABEL}\nTemp: {TEMP} K")

col1, col2 = st.columns(2)
with col1: energy_files = st.file_uploader("1. Energy Logs", accept_multiple_files=True, key="eng")
with col2: sr_files = st.file_uploader("2. SR Logs", accept_multiple_files=True, key="sr")

data_map = {}
if energy_files:
    for f in energy_files:
        val = extract_energy(f.getvalue().decode("utf-8"))
        if val: data_map[get_base_id(f.name)] = {"name": f.name, "energy": val, "sr": None}
if sr_files:
    for f in sr_files:
        file_id = get_base_id(f.name)
        val = extract_sr(f.getvalue().decode("utf-8"))
        if val:
            if file_id in data_map: data_map[file_id]["sr"] = val
            else: data_map[file_id] = {"name": f.name, "energy": None, "sr": val}

ready_data = [{"ID": k, "File": v["name"], "Energy_Ha": v["energy"], "Raw_SR": v["sr"]} 
              for k, v in data_map.items() if v["energy"] is not None and v["sr"] is not None]

if ready_data:
    df = pd.DataFrame(ready_data)
    min_e = df["Energy_Ha"].min()
    df["dG_kcal_mol"] = (df["Energy_Ha"] - min_e) * AU_TO_KCAL
    df["Pop_percent"] = (df["dG_kcal_mol"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                         df["dG_kcal_mol"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
    df["Contribution"] = df["Raw_SR"] * (df["Pop_percent"] / 100)
    final_sr = df["Contribution"].sum()

    st.write("---")
    res_col, plot_col = st.columns([2, 3])
    with res_col:
        st.subheader("📊 Summary")
        st.table(df[["ID", "dG_kcal_mol", "Pop_percent", "Raw_SR", "Contribution"]])
        diff = final_sr - exp_val if exp_val != 0 else None
        st.metric(label="Boltzmann Averaged Alpha_D", value=f"{final_sr:.2f}", 
                  delta=f"{diff:.2f} vs Exp." if diff is not None else None)

    with plot_col:
        fig = px.scatter(df, x="dG_kcal_mol", y="Raw_SR", size="Pop_percent", color="Pop_percent",
                         hover_name="ID", template="plotly_white", color_continuous_scale="Viridis")
        fig.add_hline(y=final_sr, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)

    # --- Excel-Friendly CSV Export ---
    summary_row = pd.DataFrame([{
        "ID": "TOTAL_AVERAGE", 
        "File": f"Result for {WAVELENGTH_LABEL}",
        "Raw_SR": final_sr,
        "Contribution": final_sr,
        "Pop_percent": 100.0
    }])
    csv_df = pd.concat([df, summary_row], ignore_index=True)
    
    # encoding='utf-8-sig' makes it readable in Excel without mojibake
    csv_output = csv_df.to_csv(index=False, encoding='utf-8-sig')
    
    st.download_button(
        label="Download SI-Ready CSV (Excel OK)", 
        data=csv_output, 
        file_name=f"SR_Analysis_v2.6.4_{final_sr:.1f}.csv",
        mime="text/csv"
    )