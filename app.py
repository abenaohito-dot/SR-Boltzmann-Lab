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
AU_TO_KCAL = 627.5095
WAVELENGTH = "589.3 nm"

def extract_energy(content):
    # Search for Free Energy (Opt/Freq level)
    match = re.search(r"Sum of electronic and thermal Free Energies=\s+(-?\d+\.\d+)", content)
    if not match:
        match = re.search(r"SCF Done:.*?=\s+(-?\d+\.\d+)", content)
    return float(match.group(1)) if match else None

def extract_sr(content):
    # Search for Specific Rotation (TD-DFT level)
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_name(filename):
    # Optimized for CompXX_X-X_X format
    match = re.search(r"(Comp\d+_[A-Z]-[A-Z]_\d+)", filename, re.IGNORECASE)
    return match.group(1) if match else re.sub(r"\.(log|out)$", "", filename, flags=re.IGNORECASE)

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v2.2", layout="wide")
st.title("SR-Boltzmann-Lab v2.2")
st.markdown(f"**Logical Analysis of Specific Rotation for {WAVELENGTH}**")

# Sidebar for precise method tracking
with st.sidebar:
    st.header("1. Experimental Reference")
    exp_val = st.number_input("Experimental [α]D (deg.)", value=0.0, step=0.1)
    
    st.divider()
    st.header("2. Computational Levels")
    st.info(f"""
    **Opt/Freq:** ωB97X-D/def2-SVP/SMD(MeOH)
    
    **SR (TD-DFT):** ωB97X-D/def2-TZVP/SMD(MeOH)
    
    **Temp:** {TEMP} K
    """)

# Dual File Uploaders
col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Energy Logs (SVP)")
    energy_files = st.file_uploader("Upload Opt/Freq files", accept_multiple_files=True, key="eng")
with col2:
    st.subheader("2. SR Logs (TZVP)")
    sr_files = st.file_uploader("Upload TD-DFT files", accept_multiple_files=True, key="sr")

# --- Processing Logic ---
data_map = {}
if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val:
            data_map[get_base_name(f.name)] = {"energy": val, "sr": None}

if sr_files:
    for f in sr_files:
        base = get_base_name(f.name)
        content = f.getvalue().decode("utf-8")
        val = extract_sr(content)
        if val:
            if base in data_map:
                data_map[base]["sr"] = val
            else:
                data_map[base] = {"energy": None, "sr": val}

ready_data = []
for name, v in data_map.items():
    if v["energy"] is not None and v["sr"] is not None:
        ready_data.append({"Conformer": name, "Energy (Ha)": v["energy"], "SR Value": v["sr"]})

# --- Results Rendering ---
st.write("---")
is_ready = len(ready_data) > 0
final_sr = 0.0
csv_buffer = ""
plot_buffer = b""

res_col, plot_col = st.columns([2, 3])

if is_ready:
    df = pd.DataFrame(ready_data)
    min_e = df["Energy (Ha)"].min()
    df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
    df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                     df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
    df["Contribution"] = df["SR Value"] * (df["Pop (%)"] / 100)
    final_sr = df["Contribution"].sum()

    with res_col:
        st.subheader("📊 Numerical Summary")
        st.table(df[["Conformer", "ΔG (kcal/mol)", "Pop (%)", "SR Value"]])
        st.metric(f"Boltzmann Averaged [α]D ({WAVELENGTH})", f"{final_sr:.2f} deg.")

    with plot_col:
        st.subheader("📈 Interactive Bubble Plot (Hover for ID)")
        # Plotly for Interactive Visualization
        fig = px.scatter(df, x="ΔG (kcal/mol)", y="SR Value",
                         size="Pop (%)", color="Pop (%)",
                         hover_name="Conformer",
                         hover_data={"ΔG (kcal/mol)": ":.2f", "SR Value": ":.1f", "Pop (%)": ":.1f%"},
                         color_continuous_scale="Viridis",
                         size_max=50,
                         template="plotly_white")
        
        # Reference lines
        fig.add_hline(y=final_sr, line_dash="dash", line_color="red", 
                      annotation_text=f"Calc. Avg ({final_sr:.1f})")
        if exp_val != 0:
            fig.add_hline(y=exp_val, line_dash="dot", line_color="blue", 
                          annotation_text=f"Exp. ({exp_val:.1f})")
            
        fig.update_layout(xaxis_title="Relative Gibbs Free Energy (kcal/mol)",
                          yaxis_title=f"Specific Rotation [α]D ({WAVELENGTH})")
        
        st.plotly_chart(fig, use_container_width=True)

    # Export Preparation
    csv_df = df.copy()
    summary = pd.DataFrame([{"Conformer": "TOTAL/AVERAGE", "SR Value": final_sr}], index=[len(df)])
    csv_buffer = pd.concat([csv_df, summary]).to_csv(index=False)
else:
    st.info("Awaiting matched Energy (SVP) and SR (TZVP) log pairs...")

# --- Persistent Output Buttons ---
st.divider()
dl1, dl2 = st.columns(2)
with dl1:
    st.download_button("Download SI-Data (CSV)", data=csv_buffer, 
                       file_name=f"SR_Final_{final_sr:.1f}.csv", disabled=not is_ready)
with dl2:
    st.info("Note: Use the camera icon in the plot above to save as PNG for publication.")