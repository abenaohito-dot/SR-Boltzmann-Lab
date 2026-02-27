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
st.set_page_config(page_title="SR-Boltzmann-Lab v2.0", layout="wide")
st.title("SR-Boltzmann-Lab v2.0")
st.markdown(f"**Conformer Analysis & Boltzmann Distribution for {WAVELENGTH}**")

# Sidebar
with st.sidebar:
    st.header("1. Experimental Reference")
    exp_val = st.number_input("Experimental [α]D (deg.)", value=0.0, step=0.1, help="If provided, shown as a dashed line in the plot.")
    st.divider()
    st.header("2. Parameters")
    st.info(f"Method: ωB97X-D/def2-TZVP/SMD\n\nTemp: {TEMP} K\n\nR: {GAS_CONST}")

col1, col2 = st.columns(2)
with col1:
    energy_files = st.file_uploader("1. Energy Data (Opt/Freq)", accept_multiple_files=True, key="eng")
with col2:
    sr_files = st.file_uploader("2. SR Data (TD-DFT)", accept_multiple_files=True, key="sr")

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
pending_data = []
for name, v in data_map.items():
    if v["energy"] is not None and v["sr"] is not None:
        ready_data.append({"Conformer": name, "Energy (Ha)": v["energy"], "SR Value": v["sr"]})
    else:
        status = "Waiting for SR" if v["sr"] is None else "Waiting for Energy"
        pending_data.append({"ID": name, "Status": status})

# --- Outputs ---
st.write("---")
is_ready = len(ready_data) > 0
final_sr = 0.0
csv_buffer = ""
plot_buffer = b""

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
        st.subheader("📊 Interim Boltzmann Results")
        st.table(df[["Conformer", "ΔG (kcal/mol)", "Pop (%)", "SR Value"]])
        st.metric("Boltzmann Averaged [α]D", f"{final_sr:.2f} deg.")
        if pending_data:
            st.warning(f"Incomplete pairs: {len(pending_data)}")
            st.dataframe(pd.DataFrame(pending_data), hide_index=True)

    with plot_col:
        st.subheader("📈 Conformer Distribution Plot")
        fig, ax = plt.subplots(figsize=(6, 5))
        
        # Bubble Plot: X=Rel Energy, Y=SR, Size=Population
        scatter = ax.scatter(df["ΔG (kcal/mol)"], df["SR Value"], 
                            s=df["Pop (%)"] * 20, # Scale size for visibility
                            c=df["Pop (%)"], cmap='viridis', alpha=0.7, edgecolors="black")
        
        # Horizontal lines for Weighted Average and Experimental
        ax.axhline(final_sr, color='red', linestyle='--', linewidth=1.5, label=f'Boltzmann Avg ({final_sr:.1f})')
        if exp_val != 0:
            ax.axhline(exp_val, color='blue', linestyle=':', linewidth=1.5, label=f'Exp. Value ({exp_val:.1f})')
            
        ax.set_xlabel("Relative Gibbs Free Energy (kcal/mol)", fontsize=10)
        ax.set_ylabel(f"Specific Rotation [α]D ({WAVELENGTH})", fontsize=10)
        ax.grid(True, linestyle=':', alpha=0.6)
        ax.legend(fontsize=9)
        
        plt.tight_layout()
        st.pyplot(fig)
        
        # Image Buffer
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=300)
        plot_buffer = buf.getvalue()

    # CSV Buffer
    csv_df = df.copy()
    summary = pd.DataFrame([{"Conformer": "TOTAL/AVERAGE", "SR Value": final_sr}], index=[len(df)])
    csv_buffer = pd.concat([csv_df, summary]).to_csv(index=False)

else:
    st.info("Drop matched Energy and SR log files to generate analysis.")

# --- Persistent Action Buttons ---
st.divider()
dl1, dl2 = st.columns(2)
with dl1:
    st.download_button("Download SI-Data (CSV)", data=csv_buffer, file_name=f"SR_Results_{final_sr:.1f}.csv", disabled=not is_ready)
with dl2:
    st.download_button("Download Analysis Plot (PNG)", data=plot_buffer, file_name="SR_Conformer_Plot.png", mime="image/png", disabled=not is_ready)