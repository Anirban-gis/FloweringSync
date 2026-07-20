"""
==========================================================
FloweringSync - Streamlit Web App
Replaces Tkinter GUI. All analysis logic unchanged.
==========================================================
"""

import os
import io
import zipfile
import tempfile
import shutil
import streamlit as st
import geopandas as gpd

from analysis import FloweringSynchronisation
from excel_export import export_excel
from shapefile_export import export_sync_shapefile
from spatial import check_crs

# ---------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------
st.set_page_config(
    page_title="FloweringSync – Flowering Synchronisation Analysis",
    page_icon="🌾",
    layout="wide",
)

# ---------------------------------------------------------------
# CUSTOM CSS  (dark/neon theme matching original desktop app)
# ---------------------------------------------------------------
st.markdown("""
<style>
  /* ── Global background ── */
  .stApp { background: #050b08; color: #E8FFE8; }

  /* ── Sidebar ── */
  [data-testid="stSidebar"] {
    background: #071209;
    border-right: 1px solid #0DF024;
  }

  /* ── Card / section boxes ── */
  .glass-card {
    background: rgba(10,26,14,0.85);
    border: 1.5px solid #0DF024;
    border-radius: 14px;
    padding: 20px 24px 18px 24px;
    margin-bottom: 18px;
  }
  .section-title {
    color: #0DF024;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1.5px;
    margin-bottom: 10px;
  }

  /* ── Buttons ── */
  .stButton > button {
    background: #061008;
    color: #E8FFE8;
    border: 1.5px solid #2a6040;
    border-radius: 8px;
    font-weight: 600;
  }
  .stButton > button:hover {
    background: #0a2a12;
    border-color: #0DF024;
    color: #0DF024;
  }

  /* ── Selectbox / number input ── */
  .stSelectbox > div, .stNumberInput > div input, .stTextInput > div input {
    background: #0d2a16 !important;
    color: #E8FFE8 !important;
    border-color: #0DF024 !important;
  }

  /* ── Progress bar ── */
  .stProgress > div > div { background: #0DF024; }

  /* ── File uploader ── */
  [data-testid="stFileUploader"] {
    background: #0d2a16;
    border: 1.5px dashed #0DF024;
    border-radius: 10px;
  }

  /* ── Log box ── */
  .log-box {
    background: #071209;
    border: 1px solid #1a4028;
    border-radius: 10px;
    padding: 14px 16px;
    font-family: 'Cascadia Mono', 'Courier New', monospace;
    font-size: 13px;
    color: #E8FFE8;
    max-height: 380px;
    overflow-y: auto;
    white-space: pre-wrap;
  }
  .log-info    { color: #60C8FF; }
  .log-success { color: #0DF024; font-weight: bold; }
  .log-warn    { color: #FFB347; }
  .log-error   { color: #FF4444; font-weight: bold; }
  .log-muted   { color: #4A8A60; }

  /* ── Page title ── */
  .page-title {
    font-size: 2.3rem;
    font-weight: 800;
    color: #FF6B35;
    margin-bottom: 2px;
  }
  .page-subtitle {
    font-size: 1.05rem;
    color: #A0D8FF;
    margin-bottom: 28px;
  }

  /* ── Metric chips ── */
  [data-testid="stMetric"] {
    background: #0d2a16;
    border: 1px solid #0DF024;
    border-radius: 10px;
    padding: 10px 14px;
  }
  [data-testid="stMetricLabel"] { color: #7FD4A0; font-size: 12px; }
  [data-testid="stMetricValue"] { color: #0DF024; font-size: 1.6rem; font-weight: 800; }

  /* ── Tabs ── */
  .stTabs [data-baseweb="tab"] { color: #7FD4A0; }
  .stTabs [aria-selected="true"] { color: #0DF024; border-bottom-color: #0DF024; }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------
def save_upload_to_temp(uploaded_file, suffix=".shp"):
    """Write an uploaded file to a temp location and return path."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.read())
    tmp.flush()
    tmp.close()
    return tmp.name


def save_shapefile_bundle(uploaded_files, prefix):
    """
    A shapefile needs .shp + .dbf + .shx (and optionally .prj .cpg).
    Save all uploaded companion files to the same temp directory and
    return the path to the .shp file.
    """
    tmpdir = tempfile.mkdtemp()
    shp_path = None
    for uf in uploaded_files:
        dest = os.path.join(tmpdir, f"{prefix}{os.path.splitext(uf.name)[1]}")
        with open(dest, "wb") as f:
            f.write(uf.read())
        if uf.name.lower().endswith(".shp"):
            shp_path = dest
    return shp_path


def colorize_log(message):
    """Return HTML-colored log line."""
    low = message.lower()
    if "error" in low:
        cls = "log-error"
    elif any(k in low for k in ("crop flowering sync", "exported", "finished", "loaded")):
        cls = "log-success"
    elif any(k in low for k in ("outside distance", "other crop", "skipped", "warning", "no flower")):
        cls = "log-warn"
    elif message.startswith("-"):
        cls = "log-muted"
    else:
        cls = "log-info"
    import html
    return f'<span class="{cls}">{html.escape(message)}</span>'


def shapefile_to_zip(shp_path):
    """Bundle all shapefile components into a ZIP and return bytes."""
    base = os.path.splitext(shp_path)[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in (".shp", ".dbf", ".shx", ".prj", ".cpg"):
            candidate = base + ext
            if os.path.exists(candidate):
                zf.write(candidate, os.path.basename(candidate))
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------
# SESSION STATE
# ---------------------------------------------------------------
for key, default in [
    ("iso_gdf", None), ("sur_gdf", None),
    ("iso_fields", []), ("sur_fields", []),
    ("log_lines", []), ("results", None), ("stats", None),
    ("excel_bytes", None), ("shp_zip_bytes", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ---------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------
st.markdown('<div class="page-title">🌾 Flowering Synchronisation Analysis</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Isolation vs. Surrounding Plot Flowering Overlap</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------
# SIDEBAR  –  Upload shapefiles
# ---------------------------------------------------------------
with st.sidebar:
    st.markdown("### 📂 Upload Shapefiles")
    st.caption("Upload all companion files for each shapefile (.shp .dbf .shx .prj)")

    st.markdown("#### Isolation Plot")
    iso_files = st.file_uploader(
        "Isolation shapefile bundle",
        accept_multiple_files=True,
        key="iso_upload",
        label_visibility="collapsed",
    )

    st.markdown("#### Surrounding Plot")
    sur_files = st.file_uploader(
        "Surrounding shapefile bundle",
        accept_multiple_files=True,
        key="sur_upload",
        label_visibility="collapsed",
    )

    if st.button("⬆ Load Shapefiles", use_container_width=True):
        errors = []
        if not iso_files:
            errors.append("No Isolation files uploaded.")
        if not sur_files:
            errors.append("No Surrounding files uploaded.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                iso_shp = save_shapefile_bundle(iso_files, "isolation")
                if iso_shp is None:
                    st.error("No .shp file found in Isolation upload.")
                else:
                    st.session_state.iso_gdf = gpd.read_file(iso_shp)
                    cols = [c for c in st.session_state.iso_gdf.columns if c != "geometry"]
                    st.session_state.iso_fields = cols
                    st.session_state.log_lines.append(f"Isolation layer loaded — {len(st.session_state.iso_gdf)} records | CRS: {st.session_state.iso_gdf.crs}")
                    st.success(f"✅ Isolation: {len(st.session_state.iso_gdf)} records")

                sur_shp = save_shapefile_bundle(sur_files, "surrounding")
                if sur_shp is None:
                    st.error("No .shp file found in Surrounding upload.")
                else:
                    st.session_state.sur_gdf = gpd.read_file(sur_shp)
                    cols2 = [c for c in st.session_state.sur_gdf.columns if c != "geometry"]
                    st.session_state.sur_fields = cols2
                    st.session_state.log_lines.append(f"Surrounding layer loaded — {len(st.session_state.sur_gdf)} records | CRS: {st.session_state.sur_gdf.crs}")
                    st.success(f"✅ Surrounding: {len(st.session_state.sur_gdf)} records")
            except Exception as ex:
                st.error(f"Error loading shapefiles: {ex}")

    if st.session_state.iso_gdf is not None:
        st.info(f"**Isolation** ✅ {len(st.session_state.iso_gdf)} records")
    if st.session_state.sur_gdf is not None:
        st.info(f"**Surrounding** ✅ {len(st.session_state.sur_gdf)} records")

    st.divider()
    st.caption("Developed by Anirban Das")


# ---------------------------------------------------------------
# MAIN CONTENT — three tabs
# ---------------------------------------------------------------
tab_setup, tab_run, tab_results = st.tabs(["⚙ Setup", "▶ Run Analysis", "📊 Results"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 – SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_setup:
    st.markdown('<div class="glass-card"><div class="section-title">ISOLATION PLOT — FIELD MAPPING</div>', unsafe_allow_html=True)

    iso_fields = st.session_state.iso_fields or ["(load shapefile first)"]
    col1, col2 = st.columns(2)
    with col1:
        iso_id    = st.selectbox("Plot ID column",     iso_fields, key="iso_id")
        iso_crop  = st.selectbox("Crop column",        iso_fields, key="iso_crop")
    with col2:
        iso_start = st.selectbox("Flower Start column", iso_fields, key="iso_start")
        iso_end   = st.selectbox("Flower End column",   iso_fields, key="iso_end")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="glass-card"><div class="section-title">SURROUNDING PLOT — FIELD MAPPING</div>', unsafe_allow_html=True)
    sur_fields = st.session_state.sur_fields or ["(load shapefile first)"]
    col3, col4 = st.columns(2)
    with col3:
        sur_id    = st.selectbox("Plot ID column",     sur_fields, key="sur_id")
        sur_crop  = st.selectbox("Crop column",        sur_fields, key="sur_crop")
    with col4:
        sur_start = st.selectbox("Flower Start column", sur_fields, key="sur_start")
        sur_end   = st.selectbox("Flower End column",   sur_fields, key="sur_end")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="glass-card"><div class="section-title">ANALYSIS SETTINGS</div>', unsafe_allow_html=True)
    col5, col6, col7 = st.columns(3)
    with col5:
        crop_compare = st.text_input("Crop to compare", value="Maize", key="crop_compare")
    with col6:
        distance = st.number_input("Distance limit (m)", min_value=1.0, value=400.0, step=10.0, key="distance")
    with col7:
        dist_method = st.selectbox("Distance method", ["centroid", "edge"], key="dist_method")

    export_shp = st.checkbox("Also export Shapefile output", value=True, key="export_shp")
    st.markdown("</div>", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 – RUN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_run:
    ready = (st.session_state.iso_gdf is not None and st.session_state.sur_gdf is not None)

    if not ready:
        st.warning("⬅ Upload and load both shapefiles from the sidebar first.")
    else:
        st.success("Both shapefiles are loaded — ready to run.")

    run_clicked = st.button(
        "▶  RUN ANALYSIS",
        use_container_width=True,
        disabled=not ready,
        type="primary",
    )

    progress_bar = st.progress(0)
    status_text  = st.empty()
    log_placeholder = st.empty()

    if run_clicked:
        # Validate CRS
        ok, msg = check_crs(st.session_state.iso_gdf, st.session_state.sur_gdf)
        if not ok:
            st.error(f"CRS Error: {msg}")
            st.stop()

        iso_field_map = {
            "id":    st.session_state.iso_id,
            "crop":  st.session_state.iso_crop,
            "start": st.session_state.iso_start,
            "end":   st.session_state.iso_end,
        }
        sur_field_map = {
            "id":    st.session_state.sur_id,
            "crop":  st.session_state.sur_crop,
            "start": st.session_state.sur_start,
            "end":   st.session_state.sur_end,
        }

        log_lines = []

        def progress_cb(pct, msg):
            progress_bar.progress(pct)
            status_text.markdown(f"**{msg}**")

        def log_cb(msg):
            log_lines.append(msg)
            html_lines = "<br>".join(colorize_log(l) for l in log_lines[-80:])
            log_placeholder.markdown(
                f'<div class="log-box">{html_lines}</div>',
                unsafe_allow_html=True,
            )

        try:
            engine = FloweringSynchronisation(
                iso_gdf=st.session_state.iso_gdf,
                sur_gdf=st.session_state.sur_gdf,
                iso_fields=iso_field_map,
                sur_fields=sur_field_map,
                crop_compare=st.session_state.crop_compare,
                distance_limit=st.session_state.distance,
                distance_method=st.session_state.dist_method,
                progress_callback=progress_cb,
                log_callback=log_cb,
            )

            results, stats = engine.run()
            st.session_state.results = results
            st.session_state.stats   = stats
            st.session_state.log_lines = log_lines

            # ── Build Excel in memory ──
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tf:
                excel_path = tf.name
            export_excel(results, stats, excel_path)
            with open(excel_path, "rb") as f:
                st.session_state.excel_bytes = f.read()
            os.unlink(excel_path)
            log_cb("Excel exported.")

            # ── Build Shapefile ZIP in memory ──
            if st.session_state.export_shp:
                with tempfile.TemporaryDirectory() as tmpdir:
                    shp_path = os.path.join(tmpdir, "flowering_sync.shp")
                    export_sync_shapefile(
                        results,
                        st.session_state.iso_gdf,
                        st.session_state.sur_gdf,
                        iso_field_map,
                        sur_field_map,
                        shp_path,
                    )
                    st.session_state.shp_zip_bytes = shapefile_to_zip(shp_path)
                log_cb("Shapefile exported.")

            progress_bar.progress(100)
            status_text.markdown("✅ **Analysis complete!** Go to the **Results** tab to download outputs.")

        except Exception as ex:
            import traceback
            log_cb(f"ERROR: {ex}")
            log_cb(traceback.format_exc())
            st.error(f"Analysis failed: {ex}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 3 – RESULTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_results:
    if st.session_state.results is None:
        st.info("Run the analysis first to see results here.")
    else:
        stats   = st.session_state.stats
        results = st.session_state.results

        # ── Summary metrics ──
        st.markdown('<div class="section-title">SUMMARY</div>', unsafe_allow_html=True)
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Total Comparisons",   stats.get("Total comparisons made", 0))
        col_b.metric("Synchronized Pairs",  stats.get("Number of synchronized pairs", 0))
        col_c.metric("Outside Distance",    stats.get("Number outside specified distance", 0))
        col_d.metric("No Overlap",          stats.get("Number with no flowering overlap", 0))

        st.divider()

        # ── Download buttons ──
        st.markdown('<div class="section-title">DOWNLOAD OUTPUTS</div>', unsafe_allow_html=True)
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            if st.session_state.excel_bytes:
                st.download_button(
                    label="📥 Download Excel Report (.xlsx)",
                    data=st.session_state.excel_bytes,
                    file_name="FloweringSync_Results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
        with dl_col2:
            if st.session_state.shp_zip_bytes:
                st.download_button(
                    label="📥 Download Shapefile (.zip)",
                    data=st.session_state.shp_zip_bytes,
                    file_name="FloweringSync_Shapefile.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        st.divider()

        # ── Full statistics table ──
        import pandas as pd
        st.markdown('<div class="section-title">FULL STATISTICS</div>', unsafe_allow_html=True)
        st.dataframe(
            pd.DataFrame([{"Metric": k, "Value": v} for k, v in stats.items()]),
            use_container_width=True,
            hide_index=True,
        )

        # ── Preview: Synchronized pairs only ──
        st.divider()
        st.markdown('<div class="section-title">SYNCHRONIZED PAIRS PREVIEW</div>', unsafe_allow_html=True)
        df_all  = pd.DataFrame(results)
        df_sync = df_all[df_all["Remarks"] == "Crop Flowering Sync"].reset_index(drop=True)
        st.caption(f"{len(df_sync)} synchronized pairs found")
        st.dataframe(df_sync, use_container_width=True, hide_index=True)

        # ── Processing log ──
        if st.session_state.log_lines:
            st.divider()
            st.markdown('<div class="section-title">PROCESSING LOG</div>', unsafe_allow_html=True)
            html_log = "<br>".join(colorize_log(l) for l in st.session_state.log_lines)
            st.markdown(f'<div class="log-box">{html_log}</div>', unsafe_allow_html=True)
            log_text = "\n".join(st.session_state.log_lines)
            st.download_button(
                "📄 Download Log",
                data=log_text,
                file_name="FloweringSync_log.txt",
                mime="text/plain",
            )
