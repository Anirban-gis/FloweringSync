"""
==========================================================
FloweringSync - Streamlit Web App
Replaces Tkinter GUI. All analysis logic unchanged.
==========================================================
"""

import os
import io
import base64
import zipfile
import tempfile
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
# BACKGROUND IMAGE — saved permanently to disk
# The image is stored as  static/bg_image.<ext>  next to app.py.
# A small  static/bg_meta.txt  records the mime type.
# On every page load we read it from disk → always survives refresh.
# ---------------------------------------------------------------
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
BG_META_PATH = os.path.join(STATIC_DIR, "bg_meta.txt")


def _find_saved_bg():
    """Return (path, mime) of the saved background image, or (None, None)."""
    if not os.path.exists(BG_META_PATH):
        return None, None
    try:
        mime = open(BG_META_PATH).read().strip()
        ext  = ".png" if "png" in mime else ".jpg"
        path = os.path.join(STATIC_DIR, f"bg_image{ext}")
        if os.path.exists(path):
            return path, mime
    except Exception:
        pass
    return None, None


def save_bg_to_disk(img_bytes, mime):
    """Persist the background image to disk so it survives every refresh."""
    # Remove any old background files first
    for ext in (".jpg", ".png"):
        old = os.path.join(STATIC_DIR, f"bg_image{ext}")
        if os.path.exists(old):
            os.remove(old)
    ext  = ".png" if "png" in mime else ".jpg"
    path = os.path.join(STATIC_DIR, f"bg_image{ext}")
    with open(path, "wb") as f:
        f.write(img_bytes)
    with open(BG_META_PATH, "w") as f:
        f.write(mime)


def remove_bg_from_disk():
    """Delete the saved background image."""
    for ext in (".jpg", ".png"):
        p = os.path.join(STATIC_DIR, f"bg_image{ext}")
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(BG_META_PATH):
        os.remove(BG_META_PATH)


def make_bg_css(img_bytes, mime="image/jpeg"):
    """Build CSS that embeds the image as a base64 data-URI."""
    b64 = base64.b64encode(img_bytes).decode()
    return f"""
    .stApp {{
        background-image: url("data:{mime};base64,{b64}") !important;
        background-size: cover !important;
        background-position: center !important;
        background-attachment: fixed !important;
    }}
    """


# Load background from disk on EVERY page run (survives refresh & redeployment)
_bg_path, _bg_mime = _find_saved_bg()
_bg_css = ""
if _bg_path:
    try:
        _bg_css = make_bg_css(open(_bg_path, "rb").read(), _bg_mime)
    except Exception:
        _bg_css = ""

# ---------------------------------------------------------------
# CUSTOM CSS
# ---------------------------------------------------------------
BASE_CSS = """
<style>
/* ── Default app background (dark green) ── */
.stApp {
    background: #050b08;
    color: #E8FFE8;
}

/* ── Dark overlay so background image is never too bright ── */
.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    background: rgba(2, 10, 4, 0.62);
    z-index: 0;
    pointer-events: none;
}

/* ── All main content sits above overlay ── */
.block-container { position: relative; z-index: 1; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: rgba(5, 18, 8, 0.96) !important;
    border-right: 2px solid #0DF024;
}
[data-testid="stSidebar"] * { color: #E8FFE8 !important; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   PANEL CARDS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.panel-card {
    background: rgba(8, 22, 11, 0.88);
    border: 2px solid #0DF024;
    border-radius: 14px;
    padding: 0 0 18px 0;
    margin-bottom: 22px;
    box-shadow: 0 0 18px rgba(13,240,36,0.12);
}

/* ── Panel header bar (the title strip) ── */
.panel-header {
    background: linear-gradient(90deg, #0a2e12 0%, #0d3d18 100%);
    border-bottom: 2px solid #0DF024;
    border-radius: 12px 12px 0 0;
    padding: 12px 22px 10px 22px;
    margin-bottom: 16px;
}
.panel-header-title {
    color: #0DF024 !important;
    font-size: 15px !important;
    font-weight: 800 !important;
    letter-spacing: 2px !important;
    text-transform: uppercase;
    margin: 0 !important;
    display: block;
    text-shadow: 0 0 8px rgba(13,240,36,0.5);
}
.panel-body {
    padding: 0 22px 4px 22px;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   SECTION LABELS (inside cards)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.section-label {
    color: #7FD4A0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin: 14px 0 4px 0;
    border-bottom: 1px solid #1a4028;
    padding-bottom: 4px;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   STREAMLIT WIDGETS — force visible text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
label, .stSelectbox label, .stNumberInput label,
.stTextInput label, .stCheckbox label,
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] {
    color: #B8FFB8 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
}

/* Selectbox dropdown box */
.stSelectbox > div > div {
    background: #0d2a16 !important;
    color: #E8FFE8 !important;
    border: 1.5px solid #2a6040 !important;
    border-radius: 8px !important;
}
.stSelectbox > div > div > div,
.stSelectbox > div > div > div > div,
.stSelectbox span,
.stSelectbox p,
[data-testid="stSelectbox"] span,
[data-baseweb="select"] span,
[data-baseweb="select"] div {
    color: #FFFFFF !important;
    font-weight: 600 !important;
}

/* Text & number inputs */
.stTextInput > div > div > input,
.stNumberInput > div > div > input {
    background: #0d2a16 !important;
    color: #E8FFE8 !important;
    border: 1.5px solid #2a6040 !important;
    border-radius: 8px !important;
}

/* Checkbox */
.stCheckbox > label > span { color: #B8FFB8 !important; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   TABS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.stTabs [data-baseweb="tab-list"] {
    background: rgba(5,18,8,0.85);
    border-radius: 10px 10px 0 0;
    border-bottom: 2px solid #0DF024;
    gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    color: #7FD4A0 !important;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 28px;
    border-radius: 8px 8px 0 0;
}
.stTabs [aria-selected="true"] {
    color: #0DF024 !important;
    background: rgba(13,240,36,0.1) !important;
    border-bottom: 3px solid #0DF024 !important;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   BUTTONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.stButton > button {
    background: #061008 !important;
    color: #E8FFE8 !important;
    border: 1.5px solid #2a6040 !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
}
.stButton > button:hover {
    background: #0a2a12 !important;
    border-color: #0DF024 !important;
    color: #0DF024 !important;
}
[data-testid="baseButton-primary"] {
    background: linear-gradient(90deg,#062e10,#0a4018) !important;
    border: 2px solid #0DF024 !important;
    color: #0DF024 !important;
    font-size: 16px !important;
    font-weight: 800 !important;
    letter-spacing: 1px;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   FILE UPLOADER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
[data-testid="stFileUploader"] {
    background: #0d2a16 !important;
    border: 1.5px dashed #0DF024 !important;
    border-radius: 10px !important;
}
[data-testid="stFileUploader"] p,
[data-testid="stFileUploader"] span {
    color: #7FD4A0 !important;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   PROGRESS BAR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.stProgress > div > div { background: #0DF024 !important; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   METRICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
[data-testid="stMetric"] {
    background: rgba(13,42,22,0.9);
    border: 1.5px solid #0DF024;
    border-radius: 10px;
    padding: 12px 16px;
}
[data-testid="stMetricLabel"] p { color: #7FD4A0 !important; font-size: 12px !important; }
[data-testid="stMetricValue"]   { color: #0DF024 !important; font-size: 1.7rem !important; font-weight: 800 !important; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   PAGE TITLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.page-title {
    font-size: 2.4rem;
    font-weight: 900;
    color: #FF6B35;
    margin-bottom: 2px;
    text-shadow: 0 0 20px rgba(255,107,53,0.4);
}
.page-subtitle {
    font-size: 1.05rem;
    color: #A0D8FF;
    margin-bottom: 24px;
    font-style: italic;
}

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   LOG BOX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
.log-box {
    background: #071209;
    border: 1px solid #1a4028;
    border-radius: 10px;
    padding: 14px 16px;
    font-family: 'Cascadia Mono', 'Courier New', monospace;
    font-size: 12.5px;
    color: #E8FFE8;
    max-height: 380px;
    overflow-y: auto;
    white-space: pre-wrap;
    line-height: 1.7;
}
.log-info    { color: #60C8FF; }
.log-success { color: #0DF024; font-weight: bold; }
.log-warn    { color: #FFB347; }
.log-error   { color: #FF4444; font-weight: bold; }
.log-muted   { color: #4A8A60; }

/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   DIVIDER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */
hr { border-color: #1a4028 !important; }

/* info / success / warning boxes */
[data-testid="stAlert"] { background: rgba(13,42,22,0.85) !important; border-radius: 10px; }
</style>
"""

st.markdown(BASE_CSS, unsafe_allow_html=True)

# Apply background image CSS loaded from disk (always present after upload)
if _bg_css:
    st.markdown(f"<style>{_bg_css}</style>", unsafe_allow_html=True)

# ---------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------
def panel(title, content_fn):
    """Render a styled panel card with a visible header bar."""
    st.markdown(f"""
    <div class="panel-card">
        <div class="panel-header">
            <span class="panel-header-title">⬡ &nbsp; {title}</span>
        </div>
        <div class="panel-body">
    """, unsafe_allow_html=True)
    content_fn()
    st.markdown("</div></div>", unsafe_allow_html=True)


def save_shapefile_bundle(uploaded_files, prefix):
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
    import html
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
    return f'<span class="{cls}">{html.escape(message)}</span>'


def shapefile_to_zip(shp_path):
    base = os.path.splitext(shp_path)[0]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ext in (".shp", ".dbf", ".shx", ".prj", ".cpg"):
            c = base + ext
            if os.path.exists(c):
                zf.write(c, os.path.basename(c))
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------
# PAGE HEADER
# ---------------------------------------------------------------
st.markdown('<div class="page-title">🌾 Flowering Synchronisation Analysis</div>', unsafe_allow_html=True)
st.markdown('<div class="page-subtitle">Isolation vs. Surrounding Plot Flowering Overlap &nbsp;·&nbsp; Developed by Anirban Das</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------
with st.sidebar:
    st.markdown("## 📂 Upload Shapefiles")
    st.caption("Upload all companion files (.shp .dbf .shx .prj .cpg)")

    st.markdown("#### 🔵 Isolation Plot")
    iso_files = st.file_uploader(
        "iso", accept_multiple_files=True, key="iso_upload",
        label_visibility="collapsed",
    )

    st.markdown("#### 🟢 Surrounding Plot")
    sur_files = st.file_uploader(
        "sur", accept_multiple_files=True, key="sur_upload",
        label_visibility="collapsed",
    )

    if st.button("⬆  Load Shapefiles", use_container_width=True):
        errors = []
        if not iso_files: errors.append("No Isolation files uploaded.")
        if not sur_files: errors.append("No Surrounding files uploaded.")
        if errors:
            for e in errors: st.error(e)
        else:
            try:
                iso_shp = save_shapefile_bundle(iso_files, "isolation")
                if iso_shp is None:
                    st.error("No .shp in Isolation upload.")
                else:
                    st.session_state.iso_gdf = gpd.read_file(iso_shp)
                    st.session_state.iso_fields = [c for c in st.session_state.iso_gdf.columns if c != "geometry"]
                    st.session_state.log_lines.append(f"Isolation loaded — {len(st.session_state.iso_gdf)} records | CRS: {st.session_state.iso_gdf.crs}")
                    st.success(f"✅ Isolation: {len(st.session_state.iso_gdf)} records")

                sur_shp = save_shapefile_bundle(sur_files, "surrounding")
                if sur_shp is None:
                    st.error("No .shp in Surrounding upload.")
                else:
                    st.session_state.sur_gdf = gpd.read_file(sur_shp)
                    st.session_state.sur_fields = [c for c in st.session_state.sur_gdf.columns if c != "geometry"]
                    st.session_state.log_lines.append(f"Surrounding loaded — {len(st.session_state.sur_gdf)} records | CRS: {st.session_state.sur_gdf.crs}")
                    st.success(f"✅ Surrounding: {len(st.session_state.sur_gdf)} records")
            except Exception as ex:
                st.error(f"Error: {ex}")

    if st.session_state.iso_gdf is not None:
        st.info(f"**Isolation** ✅  {len(st.session_state.iso_gdf)} records")
    if st.session_state.sur_gdf is not None:
        st.info(f"**Surrounding** ✅  {len(st.session_state.sur_gdf)} records")

    st.divider()

    # ── Background image picker ──
    st.markdown("### 🖼 Background Image")
    if _bg_path:
        st.success("✅ Background image is set")
    else:
        st.caption("No background image set.")
    st.caption("Upload any JPG/PNG — stays permanently even after refresh.")
    bg_file = st.file_uploader("bg", type=["jpg", "jpeg", "png"], key="bg_upload",
                               label_visibility="collapsed")
    col_bg1, col_bg2 = st.columns(2)
    with col_bg1:
        if st.button("✅ Apply", use_container_width=True):
            if bg_file:
                mime = "image/png" if bg_file.name.lower().endswith(".png") else "image/jpeg"
                save_bg_to_disk(bg_file.read(), mime)
                st.success("Background saved!")
                st.rerun()
            else:
                st.warning("Upload an image first.")
    with col_bg2:
        if st.button("🗑 Remove", use_container_width=True):
            remove_bg_from_disk()
            st.success("Background removed.")
            st.rerun()

    st.divider()
    st.caption("© Anirban Das — FloweringSync v3")


# ---------------------------------------------------------------
# MAIN TABS
# ---------------------------------------------------------------
tab_setup, tab_run, tab_results = st.tabs(["⚙️  Setup & Field Mapping", "▶️  Run Analysis", "📊  Results & Download"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 1 – SETUP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_setup:

    # ── Isolation Panel ──
    st.markdown("""
    <div class="panel-card">
        <div class="panel-header">
            <span class="panel-header-title">🔵 &nbsp; ISOLATION PLOT — FIELD MAPPING</span>
        </div>
        <div class="panel-body">
    """, unsafe_allow_html=True)

    iso_fields = st.session_state.iso_fields or ["(load shapefile first)"]
    c1, c2 = st.columns(2)
    with c1:
        st.selectbox("Plot ID column", iso_fields, key="iso_id")
        st.selectbox("Crop column", iso_fields, key="iso_crop")
    with c2:
        st.selectbox("Flower Start column", iso_fields, key="iso_start")
        st.selectbox("Flower End column", iso_fields, key="iso_end")

    st.markdown("</div></div>", unsafe_allow_html=True)

    # ── Surrounding Panel ──
    st.markdown("""
    <div class="panel-card">
        <div class="panel-header">
            <span class="panel-header-title">🟢 &nbsp; SURROUNDING PLOT — FIELD MAPPING</span>
        </div>
        <div class="panel-body">
    """, unsafe_allow_html=True)

    sur_fields = st.session_state.sur_fields or ["(load shapefile first)"]
    c3, c4 = st.columns(2)
    with c3:
        st.selectbox("Plot ID column", sur_fields, key="sur_id")
        st.selectbox("Crop column", sur_fields, key="sur_crop")
    with c4:
        st.selectbox("Flower Start column", sur_fields, key="sur_start")
        st.selectbox("Flower End column", sur_fields, key="sur_end")

    st.markdown("</div></div>", unsafe_allow_html=True)

    # ── Analysis Settings Panel ──
    st.markdown("""
    <div class="panel-card">
        <div class="panel-header">
            <span class="panel-header-title">⚙️ &nbsp; ANALYSIS SETTINGS</span>
        </div>
        <div class="panel-body">
    """, unsafe_allow_html=True)

    c5, c6, c7 = st.columns(3)
    with c5:
        st.text_input("Crop to compare", value="Maize", key="crop_compare")
    with c6:
        st.number_input("Distance limit (m)", min_value=1.0, value=400.0, step=10.0, key="distance")
    with c7:
        st.selectbox("Distance method", ["centroid", "edge"], key="dist_method")

    st.checkbox("Also export Shapefile output", value=True, key="export_shp")
    st.markdown("</div></div>", unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAB 2 – RUN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
with tab_run:
    ready = (st.session_state.iso_gdf is not None and st.session_state.sur_gdf is not None)

    st.markdown("""
    <div class="panel-card">
        <div class="panel-header">
            <span class="panel-header-title">▶️ &nbsp; RUN FLOWERING SYNCHRONISATION ANALYSIS</span>
        </div>
        <div class="panel-body">
    """, unsafe_allow_html=True)

    if not ready:
        st.warning("⬅  Upload and load both shapefiles from the sidebar first.")
    else:
        st.success("✅  Both shapefiles loaded — ready to run.")

    run_clicked = st.button(
        "▶  RUN ANALYSIS",
        use_container_width=True,
        disabled=not ready,
        type="primary",
    )

    progress_bar    = st.progress(0)
    status_text     = st.empty()
    log_placeholder = st.empty()

    st.markdown("</div></div>", unsafe_allow_html=True)

    if run_clicked:
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
            st.session_state.results   = results
            st.session_state.stats     = stats
            st.session_state.log_lines = log_lines

            # Excel
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tf:
                excel_path = tf.name
            export_excel(results, stats, excel_path)
            with open(excel_path, "rb") as f:
                st.session_state.excel_bytes = f.read()
            os.unlink(excel_path)
            log_cb("Excel exported.")

            # Shapefile
            if st.session_state.export_shp:
                with tempfile.TemporaryDirectory() as tmpdir:
                    shp_path = os.path.join(tmpdir, "flowering_sync.shp")
                    export_sync_shapefile(
                        results,
                        st.session_state.iso_gdf,
                        st.session_state.sur_gdf,
                        iso_field_map, sur_field_map, shp_path,
                    )
                    st.session_state.shp_zip_bytes = shapefile_to_zip(shp_path)
                log_cb("Shapefile exported.")

            progress_bar.progress(100)
            status_text.markdown("✅ **Analysis complete! Go to the Results tab to download.**")

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
        import pandas as pd
        stats   = st.session_state.stats
        results = st.session_state.results

        # ── Summary metrics ──
        st.markdown("""
        <div class="panel-card">
            <div class="panel-header">
                <span class="panel-header-title">📊 &nbsp; SUMMARY</span>
            </div>
            <div class="panel-body">
        """, unsafe_allow_html=True)

        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Total Comparisons",  stats.get("Total comparisons made", 0))
        col_b.metric("Synchronized Pairs", stats.get("Number of synchronized pairs", 0))
        col_c.metric("Outside Distance",   stats.get("Number outside specified distance", 0))
        col_d.metric("No Overlap",         stats.get("Number with no flowering overlap", 0))

        st.markdown("</div></div>", unsafe_allow_html=True)

        # ── Downloads ──
        st.markdown("""
        <div class="panel-card">
            <div class="panel-header">
                <span class="panel-header-title">📥 &nbsp; DOWNLOAD OUTPUTS</span>
            </div>
            <div class="panel-body">
        """, unsafe_allow_html=True)

        dl1, dl2 = st.columns(2)
        with dl1:
            if st.session_state.excel_bytes:
                st.download_button(
                    "📥  Download Excel Report (.xlsx)",
                    data=st.session_state.excel_bytes,
                    file_name="FloweringSync_Results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
        with dl2:
            if st.session_state.shp_zip_bytes:
                st.download_button(
                    "📥  Download Shapefile (.zip)",
                    data=st.session_state.shp_zip_bytes,
                    file_name="FloweringSync_Shapefile.zip",
                    mime="application/zip",
                    use_container_width=True,
                )

        st.markdown("</div></div>", unsafe_allow_html=True)

        # ── Statistics table ──
        st.markdown("""
        <div class="panel-card">
            <div class="panel-header">
                <span class="panel-header-title">📋 &nbsp; FULL STATISTICS</span>
            </div>
            <div class="panel-body">
        """, unsafe_allow_html=True)

        st.dataframe(
            pd.DataFrame([{"Metric": k, "Value": v} for k, v in stats.items()]),
            use_container_width=True, hide_index=True,
        )

        st.markdown("</div></div>", unsafe_allow_html=True)

        # ── Sync pairs preview ──
        df_all  = pd.DataFrame(results)
        df_sync = df_all[df_all["Remarks"] == "Crop Flowering Sync"].reset_index(drop=True)

        st.markdown(f"""
        <div class="panel-card">
            <div class="panel-header">
                <span class="panel-header-title">🌿 &nbsp; SYNCHRONIZED PAIRS — {len(df_sync)} FOUND</span>
            </div>
            <div class="panel-body">
        """, unsafe_allow_html=True)

        st.dataframe(df_sync, use_container_width=True, hide_index=True)
        st.markdown("</div></div>", unsafe_allow_html=True)

        # ── Log ──
        if st.session_state.log_lines:
            st.markdown("""
            <div class="panel-card">
                <div class="panel-header">
                    <span class="panel-header-title">🖥️ &nbsp; PROCESSING LOG</span>
                </div>
                <div class="panel-body">
            """, unsafe_allow_html=True)

            html_log = "<br>".join(colorize_log(l) for l in st.session_state.log_lines)
            st.markdown(f'<div class="log-box">{html_log}</div>', unsafe_allow_html=True)
            st.download_button(
                "📄 Download Log",
                data="\n".join(st.session_state.log_lines),
                file_name="FloweringSync_log.txt",
                mime="text/plain",
            )
            st.markdown("</div></div>", unsafe_allow_html=True)
