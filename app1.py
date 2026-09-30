"""
TB Dashboard - Health Facilities (2 Pages) + MiniDock
=====================================================

How to run:
    pip install streamlit pandas plotly pydeck
    streamlit run app1.py

Place the .streamlit/config.toml folder alongside this file (sets the
base Streamlit theme colors to teal instead of the default red).

DATA SOURCE (in order of priority)
    1. A file uploaded via the sidebar.
    2. GitHub raw CSV via GITHUB_CSV_URL below.
    3. A local data.csv next to app1.py.

Expected columns:
provinsi_id, provinsi, kabupaten_id, kabupaten, jenis_fasyankes, fasyankes_id,
fasyankes, jumlah_terduga, terduga_sesuai_standar, TBC_SO, TBC_RO,
notifikasi_TBC, enrol_SO, enrol_RO, enrol, Latitude, Longitude, TCM, MiniDock

CHANGE NOTES
    - NEW variable "MiniDock" (number of MiniDock units per facility).
      It is available in the sidebar variable list, the KPI row, the map
      tooltip, and the detailed table. If the loaded CSV has no MiniDock
      column (e.g. the old data_koordinat.csv), it is filled with 0 so the
      app still runs.
    - Map: point COLOR follows the selected variable; point SIZE follows
      TCM availability (TCM_RADIUS vs BASE_RADIUS).
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import pydeck as pdk


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(page_title="TB Facilities Dashboard", layout="wide")

# IMPORTANT: this file must contain the MiniDock column. Upload
# data_koordinat3_minidock.csv to your GitHub repo and update the file
# name below (or upload the CSV through the sidebar).
GITHUB_CSV_URL = "https://raw.githubusercontent.com/Asalulzy/Dashboard_Sebaran_Fasilitas_Kesehatan_Kab_Karawang/main/data_koordinat3_minidock.csv"

BASE_RADIUS = 500   # point radius without TCM
TCM_RADIUS = 850    # point radius with TCM (slightly larger)


# ============================================================
# DESIGN: COLOR TOKENS, TYPOGRAPHY, CSS
# ============================================================

INK = "#16232E"
PAPER = "#F6F7F4"
SURFACE = "#FFFFFF"
LINE = "#DCE2DE"
TEAL = "#0B5E63"
SLATE = "#3A5A78"

SEVERITY_SCALE = ["#F2D680", "#E8A33D", "#C1642F", "#93321F", "#7A1F1B"]
SEVERITY_RGB = [
    tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    for h in SEVERITY_SCALE
]


def get_severity_colors(n_class):
    """Pick n_class colors evenly from the lightest to the darkest end."""
    if n_class <= 1:
        return [SEVERITY_SCALE[-1]], [SEVERITY_RGB[-1]]
    idx = np.round(np.linspace(0, len(SEVERITY_SCALE) - 1, n_class)).astype(int)
    return [SEVERITY_SCALE[i] for i in idx], [SEVERITY_RGB[i] for i in idx]


JENIS_COLOR_MAP = {"Puskesmas": TEAL, "Hospital": SLATE}
TEAL_RAMP = ["#CFE8E6", "#8FC6C2", "#4FA39D", "#0B5E63", "#063D40"]

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');

html, body, [class*="css"] {{ font-family: 'IBM Plex Sans', sans-serif; color: {INK}; }}
.stApp {{ background-color: {PAPER}; }}

h1 {{
    font-family: 'IBM Plex Sans', sans-serif; font-weight: 600; font-size: 2rem;
    letter-spacing: -0.01em; color: {INK}; border-top: 4px solid {TEAL};
    padding-top: 0.6rem; margin-bottom: 0.15rem;
}}
h2, h3 {{ font-family: 'IBM Plex Sans', sans-serif; font-weight: 600; color: {INK}; }}

section[data-testid="stSidebar"] {{ background-color: {SURFACE}; border-right: 1px solid {LINE}; }}
hr {{ border-top: 1px solid {LINE}; }}
.stButton>button {{ border-radius: 4px; font-weight: 500; border: 1px solid {LINE}; }}
div[data-baseweb="tag"] {{ background-color: {TEAL} !important; border-radius: 4px !important; }}

.kpi-card {{
    background-color: {SURFACE}; border: 1px solid {LINE}; border-top: 3px solid {TEAL};
    padding: 0.7rem 0.9rem; height: 100%;
}}
.kpi-label {{ font-size: 0.78rem; color: {INK}99; margin-bottom: 0.25rem; }}
.kpi-value {{ font-family: 'IBM Plex Mono', monospace; font-weight: 600; font-size: 1.5rem; color: {INK}; }}

.legend-row {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.4rem 0 1rem 0; }}
.legend-chip {{
    display: flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; color: {INK}CC;
    border: 1px solid {LINE}; padding: 0.2rem 0.55rem; background-color: {SURFACE};
    font-family: 'IBM Plex Mono', monospace;
}}
.legend-swatch {{ width: 10px; height: 10px; display: inline-block; }}
.legend-swatch-round {{ width: 10px; height: 10px; display: inline-block; border-radius: 50%; background-color: {INK}55; border: 1px solid {INK}99; }}
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def kpi_card(label, value, column):
    value_str = f"{value:,}" if isinstance(value, (int, np.integer)) else str(value)
    column.markdown(
        f"""<div class="kpi-card">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value_str}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def render_legend(labels_and_colors):
    chips = "".join(
        f'<div class="legend-chip"><span class="legend-swatch" '
        f'style="background-color:{color}"></span>{label}</div>'
        for label, color in labels_and_colors
    )
    st.markdown(f'<div class="legend-row">{chips}</div>', unsafe_allow_html=True)


def render_size_legend():
    st.markdown(
        """<div class="legend-row">
                <div class="legend-chip">
                    <span class="legend-swatch-round" style="width:8px;height:8px;"></span>
                    No mWRD (normal size)
                </div>
                <div class="legend-chip">
                    <span class="legend-swatch-round" style="width:14px;height:14px;"></span>
                    mWRD available (slightly larger size)
                </div>
            </div>""",
        unsafe_allow_html=True,
    )


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data
def load_data(path_or_url_or_buffer):
    df = pd.read_csv(path_or_url_or_buffer)
    df.columns = [c.strip() for c in df.columns]

    # "Rumah Sakit" -> "Hospital" (display only)
    if "jenis_fasyankes" in df.columns:
        df["jenis_fasyankes"] = df["jenis_fasyankes"].replace(
            {"Rumah Sakit": "Hospital", "rumah sakit": "Hospital"}
        )

    numeric_cols = [
        "jumlah_terduga", "terduga_sesuai_standar", "TBC_SO", "TBC_RO",
        "notifikasi_TBC", "enrol_SO", "enrol_RO", "enrol",
        "Latitude", "Longitude", "MiniDock",
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # MiniDock: empty -> 0; column created if missing in the CSV
    if "MiniDock" not in df.columns:
        df["MiniDock"] = 0
    df["MiniDock"] = df["MiniDock"].fillna(0).astype(int)

    if "TCM" in df.columns:
        def _tcm_to_flag(v):
            if pd.isna(v):
                return 0
            s = str(v).strip().lower()
            if s in ["", "0", "tidak", "tidak ada", "no", "false", "nan", "-"]:
                return 0
            return 1
        df["TCM_numeric"] = df["TCM"].apply(_tcm_to_flag)
    else:
        df["TCM"] = ""
        df["TCM_numeric"] = 0

    return df


def load_data_with_fallback(uploaded_file):
    if uploaded_file is not None:
        return load_data(uploaded_file), "manual upload"

    if GITHUB_CSV_URL.strip() != "":
        try:
            return load_data(GITHUB_CSV_URL), "GitHub"
        except Exception as e:
            st.sidebar.warning(f"Failed to load data from GitHub ({e}). Trying local data.csv file...")

    try:
        return load_data("data.csv"), "local file"
    except FileNotFoundError:
        return None, None


# ============================================================
# SIDEBAR - DATA SOURCE
# ============================================================

st.sidebar.header("Data Source")

uploaded = st.sidebar.file_uploader(
    "Upload data.csv (optional, overrides automatic source)", type="csv"
)

df, sumber = load_data_with_fallback(uploaded)

if df is None:
    st.error(
        "Data not found. No file was uploaded, the GitHub link failed "
        "(GITHUB_CSV_URL), and no local data.csv file was found. Please "
        "upload via the sidebar or fix GITHUB_CSV_URL in app1.py."
    )
    st.stop()

st.sidebar.caption(f"Data loaded from: **{sumber}**")


# ============================================================
# SIDEBAR - FILTER
# ============================================================

st.sidebar.header("Filter")

kab_list = sorted(df["kabupaten"].dropna().unique().tolist())
kab_selected = st.sidebar.multiselect("District/Regency", kab_list, default=kab_list)

jenis_list = sorted(df["jenis_fasyankes"].dropna().unique().tolist())
jenis_selected = st.sidebar.multiselect("Facility Type", jenis_list, default=jenis_list)


# ============================================================
# VARIABLE FOR MAP & CHARTS
# ============================================================

variabel_options = {
    "Number of Presumptive TB Cases": "jumlah_terduga",
    "Drug-Sensitive TB (DS-TB)": "TBC_SO",
    "Drug-Resistant TB (DR-TB)": "TBC_RO",
    "TB Notifications": "notifikasi_TBC",
    "DS-TB Enrollment": "enrol_SO",
    "DR-TB Enrollment": "enrol_RO",
    "Total Enrollment": "enrol",
    "mWRD Availability": "TCM_numeric",
    "MiniDock Count": "MiniDock",
}

variabel_label = st.sidebar.selectbox("Variable for map & charts", list(variabel_options.keys()))
variabel_col = variabel_options[variabel_label]


# ============================================================
# APPLY FILTER
# ============================================================

mask = df["kabupaten"].isin(kab_selected) & df["jenis_fasyankes"].isin(jenis_selected)
fdf = df[mask].copy()


# ============================================================
# HEADER & KPI
# ============================================================

st.title("Mapping of Health Facilities and Monitoring of Tuberculosis Service Indicators")
st.caption("Presumptive case, notification, and TB enrollment data per health facility")

kpi_cols = st.columns(6)
kpi_defs = [
    ("Number of Facilities", fdf["fasyankes"].nunique()),
    ("Total Presumptive Cases", int(fdf["jumlah_terduga"].sum(skipna=True))),
    ("DS-TB", int(fdf["TBC_SO"].sum(skipna=True))),
    ("DR-TB", int(fdf["TBC_RO"].sum(skipna=True))),
    ("TB Notifications", int(fdf["notifikasi_TBC"].sum(skipna=True))),
    ("MiniDock Units", int(fdf["MiniDock"].sum())),
]
for col, (label, value) in zip(kpi_cols, kpi_defs):
    kpi_card(label, value, col)

st.divider()


# ============================================================
# PAGE NAVIGATION
# ============================================================

if "page" not in st.session_state:
    st.session_state.page = "Map"

nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 4])

with nav_col1:
    if st.button("Map Page",
                 type="primary" if st.session_state.page == "Map" else "secondary",
                 use_container_width=True):
        st.session_state.page = "Map"
        st.rerun()

with nav_col2:
    if st.button("Data Analyst Page",
                 type="primary" if st.session_state.page == "Data Analyst" else "secondary",
                 use_container_width=True):
        st.session_state.page = "Data Analyst"
        st.rerun()

st.divider()


# ============================================================
# PAGE 1: MAP
# ============================================================

if st.session_state.page == "Map":

    st.subheader(f"Distribution Map: {variabel_label}")
    st.caption("Point color follows the variable selected above · Point size shows mWRD availability")

    map_df = fdf.dropna(subset=["Latitude", "Longitude", variabel_col]).copy()

    if map_df.empty:
        st.info("No data to display on the map with the current filters.")

    else:
        vals = map_df[variabel_col]
        n_unique = vals.nunique()

        # 1 unique value  -> 1 class
        # 2-5 unique      -> each unique value is its own class (binary / MiniDock)
        # > 5 unique      -> 5-class quantiles
        is_discrete = False

        if n_unique <= 1:
            n_class = 1
            class_idx = pd.Series(0, index=vals.index)
            bin_edges = np.array([vals.min(), vals.max()])

        elif n_unique <= 5:
            is_discrete = True
            sorted_unique = np.sort(vals.unique())
            n_class = len(sorted_unique)
            value_to_class = {v: i for i, v in enumerate(sorted_unique)}
            class_idx = vals.map(value_to_class)
            discrete_values = sorted_unique

        else:
            try:
                classed, bin_edges = pd.qcut(vals, q=5, retbins=True, duplicates="drop")
                n_class = classed.cat.categories.size
                class_idx = classed.cat.codes.replace(-1, 0)
            except ValueError:
                n_class = 1
                class_idx = pd.Series(0, index=vals.index)
                bin_edges = np.array([vals.min(), vals.max()])

        colors_hex, colors = get_severity_colors(n_class)

        map_df["color_r"] = class_idx.map(lambda i: colors[i][0])
        map_df["color_g"] = class_idx.map(lambda i: colors[i][1])
        map_df["color_b"] = class_idx.map(lambda i: colors[i][2])

        # Point size = TCM availability only
        map_df["radius"] = np.where(map_df["TCM_numeric"] == 1, TCM_RADIUS, BASE_RADIUS)

        legend_items = []
        if is_discrete:
            for i, v in enumerate(discrete_values):
                label = str(int(v)) if float(v).is_integer() else str(v)
                legend_items.append((label, colors_hex[i]))
        else:
            edges = np.unique(np.round(bin_edges).astype(int))
            n_edge_class = len(edges) - 1
            edge_colors_hex, _ = get_severity_colors(n_edge_class)
            for i in range(n_edge_class):
                legend_items.append((f"{edges[i]} – {edges[i+1]}", edge_colors_hex[i]))
        if legend_items:
            render_legend(legend_items)

        render_size_legend()

        view_state = pdk.ViewState(
            latitude=map_df["Latitude"].mean(),
            longitude=map_df["Longitude"].mean(),
            zoom=9,
            pitch=0,
        )

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[Longitude, Latitude]",
            get_radius="radius",
            get_fill_color="[color_r, color_g, color_b, 190]",
            pickable=True,
            stroked=True,
            get_line_color=[22, 35, 46],
            get_line_width=1,
            auto_highlight=True,
        )

        tooltip = {
            "html": f"""
            <div style="font-family:'IBM Plex Sans',Arial,sans-serif;
                        min-width:260px; max-width:320px; line-height:1.5;">
                <div style="font-size:15px; font-weight:600; margin-bottom:6px;
                            border-bottom:2px solid {TEAL}; padding-bottom:6px;">
                    {{fasyankes}}
                </div>
                <div style="font-size:12px; color:#5b6b73; margin-bottom:8px;">
                    {{kabupaten}} &middot; {{jenis_fasyankes}} &middot; mWRD: {{TCM}}
                </div>
                <table style="width:100%; border-collapse:collapse; font-size:12px;
                               font-family:'IBM Plex Mono',monospace;">
                    <tr><td style="color:#5b6b73;">Presumptive Cases</td>
                        <td style="text-align:right; font-weight:600;">{{jumlah_terduga}}</td></tr>
                    <tr><td style="color:#5b6b73;">DS-TB</td>
                        <td style="text-align:right; font-weight:600;">{{TBC_SO}}</td></tr>
                    <tr><td style="color:#5b6b73;">DR-TB</td>
                        <td style="text-align:right; font-weight:600;">{{TBC_RO}}</td></tr>
                    <tr><td style="color:#5b6b73;">TB Notifications</td>
                        <td style="text-align:right; font-weight:600;">{{notifikasi_TBC}}</td></tr>
                    <tr><td style="color:#5b6b73;">MiniDock</td>
                        <td style="text-align:right; font-weight:600;">{{MiniDock}}</td></tr>
                    <tr style="border-top:1px solid {LINE};">
                        <td style="color:#5b6b73;">Total Enrollment</td>
                        <td style="text-align:right; font-weight:600;">{{enrol}}</td></tr>
                </table>
            </div>
            """,
            "style": {
                "backgroundColor": SURFACE,
                "color": INK,
                "border": f"1px solid {LINE}",
                "borderRadius": "2px",
                "padding": "10px",
                "fontSize": "12px",
                "maxWidth": "320px",
                "whiteSpace": "normal",
            },
        }

        st.pydeck_chart(
            pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="road"),
            use_container_width=True,
            height=820,
        )


# ============================================================
# PAGE 2: DATA ANALYST
# ============================================================

else:

    st.subheader("Display Settings")

    jumlah_options = {"Top 10": 10, "Top 15": 15, "Top 50": 50, "Show All": None}
    jumlah_label = st.selectbox(
        "Number of records to display (Top Facilities chart)",
        list(jumlah_options.keys()), index=1,
    )
    jumlah_n = jumlah_options[jumlah_label]

    st.divider()

    c1, c2 = st.columns(2)

    with c1:
        judul_top = (
            f"{jumlah_label} Facilities - {variabel_label}"
            if jumlah_n is not None else f"All Facilities - {variabel_label}"
        )
        st.subheader(judul_top)

        top_df = fdf.dropna(subset=[variabel_col]).sort_values(variabel_col, ascending=False)
        if jumlah_n is not None:
            top_df = top_df.head(jumlah_n)

        chart_height = max(500, min(len(top_df) * 25, 2000))

        fig_bar = px.bar(
            top_df, x=variabel_col, y="fasyankes", orientation="h",
            color="jenis_fasyankes", text=variabel_col,
            color_discrete_map=JENIS_COLOR_MAP,
        )
        fig_bar.update_layout(
            yaxis=dict(autorange="reversed"),
            height=chart_height,
            plot_bgcolor=SURFACE,
            paper_bgcolor=SURFACE,
            font=dict(family="IBM Plex Sans", color=INK),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with c2:
        st.subheader(f"Total {variabel_label} by District/Regency")

        agg_df = fdf.groupby("kabupaten", as_index=False)[variabel_col].sum().sort_values(
            variabel_col, ascending=False
        )
        fig_kab = px.bar(agg_df, x="kabupaten", y=variabel_col)
        fig_kab.update_traces(marker_color=TEAL)
        fig_kab.update_layout(
            height=500,
            showlegend=False,
            plot_bgcolor=SURFACE,
            paper_bgcolor=SURFACE,
            font=dict(family="IBM Plex Sans", color=INK),
        )
        st.plotly_chart(fig_kab, use_container_width=True)

    st.divider()

    st.subheader("TB Cascade Comparison (Presumptive → Notification → Enrollment)")

    cascade_cols = [c for c in ["jumlah_terduga", "notifikasi_TBC", "enrol"] if c in fdf.columns]

    cascade_sum = fdf[cascade_cols].sum(skipna=True).reset_index()
    cascade_sum.columns = ["Stage", "Count"]

    fig_cascade = px.funnel(cascade_sum, x="Count", y="Stage")
    fig_cascade.update_traces(marker_color=TEAL_RAMP[:len(cascade_sum)])
    fig_cascade.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(family="IBM Plex Sans", color=INK),
    )
    st.plotly_chart(fig_cascade, use_container_width=True)

    st.divider()

    st.subheader("Detailed Data")
    st.dataframe(fdf, use_container_width=True, hide_index=True)

    csv = fdf.to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered data (CSV)", csv, "data_tb_filtered.csv", "text/csv")
