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
TEMP = 298.15              # 25.0 °C
GAS_CONST = 0.001987204    # kcal/(mol·K)
AU_TO_KCAL = 627.5095      # Conversion factor
WAVELENGTH = "589.3 nm"

def extract_energy(content):
    # Search for Free Energy from Opt/Freq calculation
    match = re.search(r"Sum of electronic and thermal Free Energies=\s+(-?\d+\.\d+)", content)
    if not match:
        match = re.search(r"SCF Done:.*?=\s+(-?\d+\.\d+)", content)
    return float(match.group(1)) if match else None

def extract_sr(content):
    """
    Extracts Specific Rotation from Gaussian TD-DFT logs.
    Priority:
    1. Optical Rotation GL (GIAO) with wavelength (most accurate)
    2. Optical Rotation GL (GIAO) static value
    3. Any wavelength-specific [Alpha] (Fallback, often GV)
    """
    # 1. First, strictly look inside the 'Optical Rotation GL:' section
    # Use re.DOTALL to scan the block until the next major section or double newline
    gl_section = re.search(r"Optical Rotation GL:.*?(?=\n\s*\n|Optical Rotation GL\*W|Optical Rotation|$)", content, re.DOTALL)
    
    if gl_section:
        section_text = gl_section.group(0)
        # Target wavelength-specific [Alpha] within the GL section
        match = re.search(r"\[Alpha\]\s+\(\s*[\d\.]+\s+A\)\s+=\s+(-?\d+\.\d+)", section_text)
        if match:
            return float(match.group(1))
        
        # Fallback to static GL if wavelength is not found
        match = re.search(r"\[Alpha\]D\s+\(static\)\s+=\s+(-?\d+\.\d+)", section_text)
        if match:
            return float(match.group(1))

    # 2. Global Fallback: Find the LAST wavelength-specific [Alpha] (usually GL in most logs)
    matches = re.findall(r"\[Alpha\]\s+\(\s*[\d\.]+\s+A\)\s+=\s+(-?\d+\.\d+)", content)
    if matches:
        return float(matches[-1])

    # 3. Final Fallback: Any [Alpha] string
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_id(filename):
    """Matches files by trailing digits, e.g., 'conf_1.log' -> '1'"""
    name = filename.lower().replace(".log", "").replace(".out", "")
    match = re.search(r"(\d+)$", name)
    return match.group(1) if match else name

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v2.6.2", layout="wide")
st.title("SR-Boltzmann-Lab v2.6.2 (GIAO Locked)")
st.markdown(f"**GIAO (GL) Specific Rotation Analysis for {WAVELENGTH}**")

# Sidebar
with st.sidebar:
    st.header("1. Experimental Reference")
    exp_val = st.number_input("Experimental [α]D (deg.)", value=0.0, step=0.1)
    st.divider()
    st.header("2. Settings")
    st.info(f"Target Temp: {TEMP} K\nPriority: Optical Rotation GL")

# Dual File Uploaders
col1, col2 = st.columns(2)
with col1:
    energy_files = st.file_uploader("1. Opt/Freq Logs (Energy)", accept_multiple_files=True, key="eng")
with col2:
    sr_files = st.file_uploader("2. TD-DFT Logs (SR)", accept_multiple_files=True, key="sr")

# --- Processing Logic ---
data_map = {}
if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val:
            data_map[get_base_id(f.name)] = {"name": f.name, "energy": val, "sr": None}

if sr_files:
    for f in sr_files:
        file_id = get_base_id(f.name)
        content = f.getvalue().decode("utf-8")
        val = extract_sr(content)
        if val:
            if file_id in data_map:
                data_map[file_id]["sr"] = val
            else:
                data_map[file_id] = {"name": f.name, "energy": None, "sr": val}

ready_data = [
    {"ID": k, "File": v["name"], "Energy (Ha)": v["energy"], "Raw SR": v["sr"]}
    for k, v in data_map.items() if v["energy"] is not None and v["sr"] is not None
]

# --- Results Rendering ---
st.write("---")
if ready_data:
    df = pd.DataFrame(ready_data)
    min_e = df["Energy (Ha)"].min()
    
    # Boltzmann Calculations
    df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
    df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                     df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
    df["Contribution"] = df["Raw SR"] * (df["Pop (%)"] / 100)
    final_sr = df["Contribution"].sum()

    res_col, plot_col = st.columns([2, 3])
    with res_col:
        st.subheader("📊 Numerical Summary")
        st.table(df[["ID", "ΔG (kcal/mol)", "Pop (%)", "Raw SR", "Contribution"]])
        st.metric("Boltzmann Averaged [α]D", f"{final_sr:.2f} deg.")

    with plot_col:
        st.subheader("📈 Interactive Plot")
        fig_px = px.scatter(df, x="ΔG (kcal/mol)", y="Raw SR", size="Pop (%)", color="Pop (%)",
                            hover_name="ID", color_continuous_scale="Viridis",
                            template="plotly_white")
        fig_px.add_hline(y=final_sr, line_dash="dash", line_color="red", annotation_text="Calc. Avg")
        if exp_val != 0:
            fig_px.add_hline(y=exp_val, line_dash="dot", line_color="blue", annotation_text="Exp.")
        st.plotly_chart(fig_px, use_container_width=True)

    # Export
    st.download_button("Download CSV Results", df.to_csv(index=False), "SR_Final_Analysis.csv")
else:
    st.info("Upload Gaussian logs. The app will pair them by ID and extract GIAO (GL) specific rotation.")