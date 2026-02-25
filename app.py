import streamlit as st
import pandas as pd
import numpy as np
import re

# --- Physical Constants ---
HARTREE_TO_KCAL = 627.5095
R_KCAL = 0.001987204
TEMP_K = 298.15

st.set_page_config(page_title="SR-Boltzmann-Lab v1.0", layout="wide")

st.title("🧪 SR-Boltzmann-Lab v1.0")
st.write("Universal Boltzmann-weighted average tool for Specific Rotation.")

# --- Slim Physics Panel ---
st.markdown(f"""
<div style="background-color: #1e1e1e; padding: 10px; border-radius: 5px; border: 1px solid #333;">
    <span style="color: #888; font-size: 0.8rem; margin-right: 20px;"><b>PHYSICS:</b></span>
    <span style="color: #aaa; font-size: 0.8rem; margin-right: 20px;">T = {TEMP_K} K</span>
    <span style="color: #aaa; font-size: 0.8rem; margin-right: 20px;">R = {R_KCAL}</span>
    <span style="color: #aaa; font-size: 0.8rem;">Conv. = {HARTREE_TO_KCAL}</span>
</div>
""", unsafe_allow_html=True)

st.write("")

# --- Flexible File Input ---
st.subheader("Step 1: Drop Gaussian Log Files")
uploaded_files = st.file_uploader("Drag and drop .log/.out files", accept_multiple_files=True)

data_list = []
if uploaded_files:
    for uploaded_file in uploaded_files:
        content = uploaded_file.read().decode("utf-8")
        alpha_match = re.search(r"\[alpha\]\s+=\s+([-+]?\d+\.\d+)", content)
        energy_match = re.search(r"Sum of electronic and thermal Free Energies=\s+([-+]?\d+\.\d+)", content)
        
        if energy_match:
            data_list.append({
                "File": uploaded_file.name,
                "Energy (Ha)": float(energy_match.group(1)),
                "Alpha": float(alpha_match.group(1)) if alpha_match else None
            })

# --- Result & Button Area (Gray-out Logic) ---
st.divider()
res_col1, res_col2 = st.columns(2)

if data_list:
    df = pd.DataFrame(data_list)
    valid_df = df.dropna(subset=['Energy (Ha)', 'Alpha']).copy()
    
    if not valid_df.empty:
        # Calculation
        min_e = valid_df['Energy (Ha)'].min()
        valid_df['dG (kcal/mol)'] = (valid_df['Energy (Ha)'] - min_e) * HARTREE_TO_KCAL
        valid_df['Weight'] = np.exp(-valid_df['dG (kcal/mol)'] / (R_KCAL * TEMP_K))
        sum_w = valid_df['Weight'].sum()
        valid_df['Pop (%)'] = (valid_df['Weight'] / sum_w) * 100
        valid_df['Contrib'] = valid_df['Alpha'] * (valid_df['Weight'] / sum_w)
        
        # Display Results
        st.subheader(f"📊 Step 2: Results ({len(valid_df)} files)")
        st.dataframe(valid_df[['File', 'Energy (Ha)', 'dG (kcal/mol)', 'Pop (%)', 'Alpha', 'Contrib']].style.format({
            'Energy (Ha)': '{:.6f}', 'dG (kcal/mol)': '{:.2f}', 'Pop (%)': '{:.1f}', 'Alpha': '{:.1f}', 'Contrib': '{:.2f}'
        }), use_container_width=True)
        
        total_sr = valid_df['Contrib'].sum()
        res_col1.metric(label="Final Boltzmann Averaged [α]D", value=f"{total_sr:.2f}")
        
        csv = valid_df.to_csv(index=False).encode('utf-8')
        res_col2.download_button("Download CSV for SI", csv, "SR_Results.csv", "text/csv")
    else:
        res_col1.metric("Final Boltzmann Averaged [α]D", "---")
        res_col2.button("Download CSV for SI (No data)", disabled=True)
        st.warning("Logs detected, but calculation is incomplete (Alpha values missing).")
else:
    # Gray-out state when no files are uploaded
    res_col1.metric("Final Boltzmann Averaged [α]D", "---")
    res_col2.button("Download CSV for SI (Awaiting data)", disabled=True)
    st.info("Awaiting log files to begin calculation.")