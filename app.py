import streamlit as st
import pandas as pd
import re
import math
import matplotlib.pyplot as plt
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
    match = re.search(r"\[Alpha\].*?=\s+(-?\d+\.\d+)\s+deg\.", content)
    return float(match.group(1)) if match else None

def get_base_name(filename):
    match = re.search(r"(Comp\d+_[A-Z]-[A-Z]_\d+)", filename, re.IGNORECASE)
    return match.group(1) if match else re.sub(r"\.(log|out)$", "", filename, flags=re.IGNORECASE)

# --- UI Layout ---
st.set_page_config(page_title="SR-Boltzmann-Lab v1.9", layout="wide")
st.title("SR-Boltzmann-Lab v1.9")

# Sidebar
with st.sidebar:
    st.header("1. Experimental Input")
    exp_val = st.number_input("Experimental [α]D (deg.)", value=0.0, step=0.1)
    st.divider()
    st.header("2. Parameters")
    st.info(f"Method: ωB97X-D/def2-TZVP/SMD\n\nTemp: {TEMP} K\n\nR: {GAS_CONST}")

col1, col2 = st.columns(2)
with col1:
    energy_files = st.file_uploader("Upload Opt/Freq logs", accept_multiple_files=True, key="eng")
with col2:
    sr_files = st.file_uploader("Upload SR logs", accept_multiple_files=True, key="sr")

# --- Logic ---
data_map = {}
if energy_files:
    for f in energy_files:
        content = f.getvalue().decode("utf-8")
        val = extract_energy(content)
        if val: data_map[get_base_name(f.name)] = {"energy": val, "sr": None}

if sr_files:
    for f in sr_files:
        base = get_base_name(f.name)
        content = f.getvalue().decode("utf-8")
        val = extract_sr(content)
        if val:
            if base in data_map: data_map[base]["sr"] = val
            else: data_map[base] = {"energy": None, "sr": val}

ready_data = []
for name, v in data_map.items():
    if v["energy"] is not None and v["sr"] is not None:
        ready_data.append({"Conformer": name, "Energy (Ha)": v["energy"], "SR Value": v["sr"]})

# Initialize variables for output
is_ready = len(ready_data) > 0
csv_buffer = ""
plot_buffer = b""
final_sr = 0.0

st.write("---")
res_col, plot_col = st.columns([1, 1])

if is_ready:
    df = pd.DataFrame(ready_data)
    min_e = df["Energy (Ha)"].min()
    df["ΔG (kcal/mol)"] = (df["Energy (Ha)"] - min_e) * AU_TO_KCAL
    df["Pop (%)"] = (df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))) / 
                     df["ΔG (kcal/mol)"].apply(lambda x: math.exp(-x / (GAS_CONST * TEMP))).sum()) * 100
    df["Contribution"] = df["SR Value"] * (df["Pop (%)"] / 100)
    final_sr = df["Contribution"].sum()

    with res_col:
        st.subheader("📊 Analysis Summary")
        st.table(df[["Conformer", "Pop (%)", "SR Value", "Contribution"]])
        st.metric("Boltzmann Averaged [α]D", f"{final_sr:.2f} deg.")
    
    with plot_col:
        st.subheader("🖼️ Comparison Plot")
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.bar(['Exp.', 'Calc.'], [exp_val, final_sr], color=['#5DADE2', '#E74C3C'], edgecolor='black', width=0.6)
        ax.axhline(0, color='black', linewidth=0.8)
        ax.set_ylabel(f'[α]D ({WAVELENGTH})')
        plt.tight_layout()
        st.pyplot(fig)
        
        # Prepare Plot Buffer
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=300)
        plot_buffer = buf.getvalue()

    # Prepare CSV Buffer
    csv_df = df.copy()
    summary = pd.DataFrame([{"Conformer": "TOTAL/AVG", "SR Value": final_sr}], index=[len(df)])
    csv_buffer = pd.concat([csv_df, summary]).to_csv(index=False)

else:
    st.info("Waiting for matched Energy and SR log files...")

# --- Persistent Output Buttons (Grayed out if not ready) ---
st.divider()
dl_col1, dl_col2 = st.columns(2)

with dl_col1:
    st.download_button(
        label="Download SI-Data (CSV)",
        data=csv_buffer,
        file_name=f"SR_Final_{final_sr:.1f}.csv",
        disabled=not is_ready,
        key="dl_csv"
    )

with dl_col2:
    st.download_button(
        label="Download Plot (PNG)",
        data=plot_buffer,
        file_name="SR_Comparison_Plot.png",
        mime="image/png",
        disabled=not is_ready,
        key="dl_plot"
    )