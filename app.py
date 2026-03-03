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
WAVELENGTH = "589.3 nm"    # Note: Target is D-line

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
    1. Optical Rotation GL (GIAO) with wavelength (e.g., 5983.0 A)
    2. Optical Rotation GL (GIAO) static value
    3. First available [Alpha] value (Fallback)
    """
    # 1. Target: Optical Rotation GL with wavelength
    # re.DOTALL is used to match across multiple lines after the header
    gl_section = re.search(r"Optical Rotation GL:.*?(?=\n\s*\n|Optical Rotation|$)", content, re.DOTALL)
    if gl_section:
        section_text = gl_section.group(0)
        # Search for wavelength-specific [Alpha] (e.g., -152.87)
        match = re.search(r"\[Alpha\]\s+\(\s*[\d\.]+\s+A\)\s+=\s+(-?\d+\.\d+)", section_text)
        if match:
            return float(match.group(1))
        
        # 2. Target: Optical Rotation GL static [Alpha]D
        match = re.search(r"\[Alpha\]D\s+\(static\)\s+=\s+(-?\d+\.\d+)", section_text)
        if match:
            return float(match.group(1))

    # 3. Fallback: Search for any [Alpha] in the file
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_id(filename):
    """
    Extracts the numerical suffix as the unique ID for pairing.
    Example: 'Comp14_R-F_1.log' -> '1'
    """
    name = filename.lower().replace(".log", "").replace(".out", "")
    match = re.search(r"(\d+)$", name)
    if match:
        return match.group(1)
    return name

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v2.6", layout="wide")
st.title("SR-Boltzmann-Lab v2.6")
st.markdown(f"**GIAO (GL) Optimized Analysis for {WAVELENGTH}**")

# Sidebar
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
    st.caption("v2.6 Priority: Optical Rotation GL (GIAO) > GV")

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

ready_data = []
for file_id, v in data_map.items():
    if v["energy"] is not None and v["sr"] is not None:
        ready_data.append({
            "ID": file_id, 
            "File": v["name"], 
            "Energy (Ha)": v["energy"], 
            "Raw SR": v["sr"]
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
    
    # Calculate Boltzmann
    df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
    df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                     df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
    
    # Calculate Contribution
    df["Contribution"] = df["Raw SR"] * (df["Pop (%)"] / 100)
    final_sr = df["Contribution"].sum()

    with res_col:
        st.subheader("📊 Numerical Summary")
        st.table(df[["ID", "ΔG (kcal/mol)", "Pop (%)", "Raw SR", "Contribution"]])
        st.metric(f"Boltzmann Averaged [α]D", f"{final_sr:.2f} deg.")

    with plot_col:
        st.subheader("📈 Interactive Analysis")
        fig_px = px.scatter(df, x="ΔG (kcal/mol)", y="Raw SR",
                            size="Pop (%)", color="Pop (%)",
                            hover_name="ID",
                            hover_data={"File": True, "Pop (%)": ":.1f%", "Contribution": ":.2f"},
                            color_continuous_scale="Viridis",
                            size_max=40, template="plotly_white")
        fig_px.add_hline(y=final_sr, line_dash="dash", line_color="red", annotation_text="Calc. Avg")
        if exp_val != 0:
            fig_px.add_hline(y=exp_val, line_dash="dot", line_color="blue", annotation_text="Exp.")
        st.plotly_chart(fig_px, use_container_width=True)

        # Static Matplotlib Plot for PNG
        fig_static, ax = plt.subplots(figsize=(6, 5), dpi=300)
        ax.scatter(df["ΔG (kcal/mol)"], df["Raw SR"], 
                   s=df["Pop (%)"] * 20, c=df["Pop (%)"], 
                   cmap='viridis', alpha=0.7, edgecolors="black")
        ax.axhline(final_sr, color='red', linestyle='--', label=f'Calc. Avg ({final_sr:.1f})')
        if exp_val != 0:
            ax.axhline(exp_val, color='blue', linestyle=':', label=f'Exp. ({exp_val:.1f})')
        ax.set_xlabel("Relative Gibbs Free Energy (kcal/mol)")
        ax.set_ylabel(f"Raw SR [α]D (GIAO)")
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(fontsize=9)
        plt.tight_layout()
        
        buf = io.BytesIO()
        fig_static.savefig(buf, format="png", dpi=300)
        plot_png_buffer = buf.getvalue()

    summary_row = pd.DataFrame([{"ID": "AVERAGED TOTAL", "Contribution": final_sr}], index=[len(df)])
    csv_buffer = pd.concat([df, summary_row]).to_csv(index=False)
else:
    st.info("Upload Gaussian logs. Priority: Optical Rotation GL (GIAO) with wavelength.")

# --- Download ---
st.divider()
dl1, dl2 = st.columns(2)
with dl1:
    st.download_button("Download SI-Data (CSV)", data=csv_buffer, 
                       file_name=f"SR_Boltzmann_v2.6_{final_sr:.1f}.csv", disabled=not is_ready)
with dl2:
    st.download_button("Download Plot (PNG)", data=plot_png_buffer, 
                       file_name="SR_Boltzmann_Plot.png", mime="image/png", disabled=not is_ready)