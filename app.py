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
    # Search for Specific Rotation from TD-DFT calculation
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_id(filename):
    """
    Extracts the numerical suffix as the unique ID for pairing.
    Example: 'Comp14_R-F_1.log' -> '1', 'Structure_opt_2.out' -> '2'
    """
    # Remove extension and lowercase
    name = filename.lower().replace(".log", "").replace(".out", "")
    # Search for digits at the very end of the string
    match = re.search(r"(\d+)$", name)
    if match:
        return match.group(1)
    return name # Fallback to full name if no digits found

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v2.5", layout="wide")
st.title("SR-Boltzmann-Lab v2.5")
st.markdown(f"**Flexible Numerical Matching for {WAVELENGTH}**")

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
    st.caption("Pairing logic: Matches files by the last digit in their names.")

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
# Process Energy files first to establish the IDs
if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val:
            data_map[get_base_id(f.name)] = {"name": f.name, "energy": val, "sr": None}

# Match SR files based on the numerical ID
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

ready_data = []
for file_id, v in data_map.items():
    if v["energy"] is not None and v["sr"] is not None:
        ready_data.append({
            "ID": file_id, 
            "File": v["name"], 
            "Energy (Ha)": v["energy"], 
            "SR Value": v["sr"]
        })

# --- Results Rendering ---
st.write("---")
is_ready = len(ready_data) > 0
final_sr = 0.0
csv_buffer = ""
plot_png_buffer = b""

res_col, plot_col = st.columns([2, 3])

if is_ready:
    df = pd.DataFrame(ready_data)
    min_e = df["Energy (Ha)"].min()
    # Calculate Boltzmann distribution
    df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
    df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                     df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
    df["Contribution"] = df["SR Value"] * (df["Pop (%)"] / 100)
    final_sr = df["Contribution"].sum()

    with res_col:
        st.subheader("📊 Numerical Summary")
        st.table(df[["ID", "ΔG (kcal/mol)", "Pop (%)", "SR Value"]])
        st.metric(f"Boltzmann Averaged [α]D ({WAVELENGTH})", f"{final_sr:.2f} deg.")

    with plot_col:
        st.subheader("📈 Interactive Analysis")
        # Plotly for ID identification
        fig_px = px.scatter(df, x="ΔG (kcal/mol)", y="SR Value",
                            size="Pop (%)", color="Pop (%)",
                            hover_name="ID",
                            hover_data={"File": True, "ΔG (kcal/mol)": ":.2f", "Pop (%)": ":.1f%"},
                            color_continuous_scale="Viridis",
                            size_max=40, template="plotly_white")
        fig_px.add_hline(y=final_sr, line_dash="dash", line_color="red")
        if exp_val != 0:
            fig_px.add_hline(y=exp_val, line_dash="dot", line_color="blue")
        st.plotly_chart(fig_px, use_container_width=True)

        # Static Matplotlib Plot for PNG
        fig_static, ax = plt.subplots(figsize=(6, 5), dpi=300)
        ax.scatter(df["ΔG (kcal/mol)"], df["SR Value"], 
                   s=df["Pop (%)"] * 20, c=df["Pop (%)"], 
                   cmap='viridis', alpha=0.7, edgecolors="black")
        ax.axhline(final_sr, color='red', linestyle='--', label=f'Calc. Avg ({final_sr:.1f})')
        if exp_val != 0:
            ax.axhline(exp_val, color='blue', linestyle=':', label=f'Exp. ({exp_val:.1f})')
        ax.set_xlabel("Relative Gibbs Free Energy (kcal/mol)")
        ax.set_ylabel(f"Specific Rotation [α]D ({WAVELENGTH})")
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(fontsize=9)
        plt.tight_layout()
        
        buf = io.BytesIO()
        fig_static.savefig(buf, format="png", dpi=300)
        plot_png_buffer = buf.getvalue()

    # CSV Export
    csv_df = df.copy()
    summary = pd.DataFrame([{"ID": "TOTAL", "SR Value": final_sr}], index=[len(df)])
    csv_buffer = pd.concat([csv_df, summary]).to_csv(index=False)
else:
    st.info("Drop Gaussian logs. Files will be paired by their trailing numbers (e.g., '_1').")

# --- Persistent Output Buttons ---
st.divider()
dl1, dl2 = st.columns(2)
with dl1:
    st.download_button("Download SI-Data (CSV)", data=csv_buffer, 
                       file_name=f"SR_Final_{final_sr:.1f}.csv", disabled=not is_ready)
with dl2:
    st.download_button("Download Plot (High-Res PNG)", data=plot_png_buffer, 
                       file_name="SR_Boltzmann_Plot.png", mime="image/png", disabled=not is_ready)