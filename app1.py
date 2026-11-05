"""
TB Dashboard - Health Facilities (2 Pages) + MiniDock
=====================================================

Cara menjalankan:
    pip install streamlit pandas plotly pydeck
    streamlit run app1.py

Sumber data (urutan prioritas):
    1. File yang diupload lewat sidebar.
    2. CSV di GitHub (GITHUB_CSV_URL di bawah).
    3. File lokal TB_Data_JawaBarat_Banten.csv atau data.csv di samping app1.py.

Nama kolom CSV dikenali otomatis, baik versi asli ("Provinsi", "Kabupaten/Kota",
"TBC SO", "Enrol DS-TB", ...) maupun versi snake_case (provinsi, kabupaten,
TBC_SO, enrol_SO, ...). Lihat COLUMN_ALIASES.

Untuk Streamlit Cloud, requirements.txt minimal:
    streamlit
    pandas
    numpy
    plotly
    pydeck
"""

import re

import numpy as np
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st


# ============================================================
# CONFIG
# ============================================================
st.set_page_config(page_title="TB Facilities Dashboard", layout="wide")

# Nama file harus sama persis dengan yang di-upload ke repo GitHub
# (di root branch main). Kalau nama file atau foldernya beda, ubah di sini.
GITHUB_CSV_URL = (
    "https://raw.githubusercontent.com/Asalulzy/"
    "Dashboard_Sebaran_Fasilitas_Kesehatan_Kab_Karawang/main/"
    "data_koordinat3_minidock.csv"
)
LOCAL_CANDIDATES = ["TB_Data_JawaBarat_Banten.csv", "data.csv"]

BASE_RADIUS = 500   # radius titik tanpa TCM (meter)
TCM_RADIUS = 850    # radius titik dengan TCM (sedikit lebih besar)


# ============================================================
# HELPER KOMPATIBILITAS STREAMLIT
# ============================================================
def stretch(fn, *args, **kwargs):
    """Lebar penuh: pakai width='stretch' (Streamlit baru), fallback ke
    use_container_width=True (Streamlit lama)."""
    try:
        return fn(*args, width="stretch", **kwargs)
    except Exception:
        return fn(*args, use_container_width=True, **kwargs)


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
    """Pilih n_class warna merata dari ujung terang ke ujung gelap."""
    if n_class <= 1:
        return [SEVERITY_SCALE[-1]], [SEVERITY_RGB[-1]]
    idx = np.round(np.linspace(0, len(SEVERITY_SCALE) - 1, n_class)).astype(int)
    return [SEVERITY_SCALE[i] for i in idx], [SEVERITY_RGB[i] for i in idx]


JENIS_COLOR_MAP = {
    "Puskesmas": TEAL,
    "Hospital": SLATE,
    "Klinik": "#C1642F",
    "Dokter Praktik Mandiri": "#E8A33D",
    "Lapas/Rutan": "#6B7280",
    "BP4/ BBKPM/ BKPM": "#93321F",
    "Balai Pengobatan": "#8A6BA8",
}
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
# Nama kolom (dinormalisasi: huruf kecil, tanpa spasi/simbol) -> nama standar app.
COLUMN_ALIASES = {
    "provid": "provinsi_id", "provinsiid": "provinsi_id",
    "provinsi": "provinsi",
    "kabid": "kabupaten_id", "kabupatenid": "kabupaten_id",
    "kabupatenkota": "kabupaten", "kabupaten": "kabupaten",
    "jenisfasyankes": "jenis_fasyankes",
    "faskesid": "fasyankes_id", "fasyankesid": "fasyankes_id",
    "fasyankes": "fasyankes",
    "alamatlengkap": "alamat",
    "jumlahterduga": "jumlah_terduga",
    "terdugasesuaistandar": "terduga_sesuai_standar",
    "tbcso": "TBC_SO",
    "tbcro": "TBC_RO",
    "notifikasitbc": "notifikasi_TBC",
    "enrol": "enrol",
    "enroldstb": "enrol_SO", "enrolso": "enrol_SO",
    "enroldrtb": "enrol_RO", "enrolro": "enrol_RO",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "tcm": "TCM",
    "minidock": "MiniDock",
}

REQUIRED_COLUMNS = [
    "provinsi", "kabupaten", "jenis_fasyankes", "fasyankes",
    "jumlah_terduga", "TBC_SO", "TBC_RO", "notifikasi_TBC", "enrol",
    "Latitude", "Longitude",
]

load_errors = []


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def standardize_columns(df):
    """Buang BOM/spasi di nama kolom, lalu samakan ke nama standar app."""
    df.columns = [str(c).replace("﻿", "").strip() for c in df.columns]
    rename = {}
    for c in df.columns:
        target = COLUMN_ALIASES.get(_norm(c))
        if target and target != c:
            rename[c] = target
    return df.rename(columns=rename)


@st.cache_data(ttl=600, show_spinner="Membaca data...")
def load_data(path_or_buffer):
    df = pd.read_csv(path_or_buffer, encoding="utf-8-sig")
    df = standardize_columns(df)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Kolom tidak ditemukan: {missing}. Kolom di file: {list(df.columns)}"
        )

    # Rapikan spasi/tab di kolom teks
    for c in df.columns:
        if pd.api.types.is_object_dtype(df[c]) or pd.api.types.is_string_dtype(df[c]):
            df[c] = df[c].str.replace(r"[\t\r\n]+", " ", regex=True).str.strip()

    # "Rumah Sakit" -> "Hospital" (hanya tampilan)
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

    # MiniDock: kosong -> 0; kolom dibuat kalau tidak ada di CSV
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
        df["TCM"] = df["TCM"].fillna("-").astype(str)
    else:
        df["TCM"] = "-"
        df["TCM_numeric"] = 0

    # Label unik fasilitas (nama bisa kembar antar kabupaten)
    df["fasyankes_label"] = df["fasyankes"].astype(str) + " (" + df["kabupaten"].astype(str) + ")"

    return df


def load_data_with_fallback(uploaded_file):
    if uploaded_file is not None:
        return load_data(uploaded_file), "manual upload"

    if GITHUB_CSV_URL.strip() != "":
        try:
            return load_data(GITHUB_CSV_URL), "GitHub"
        except Exception as e:
            load_errors.append(f"GitHub: {e}")
            st.sidebar.warning(f"Gagal memuat dari GitHub ({e}). Mencoba file lokal...")

    for name in LOCAL_CANDIDATES:
        try:
            return load_data(name), f"local file ({name})"
        except FileNotFoundError:
            continue
        except Exception as e:
            load_errors.append(f"{name}: {e}")

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
        "Data tidak bisa dimuat. Tidak ada file yang diupload, link GitHub gagal "
        "(cek GITHUB_CSV_URL: nama file, branch, dan apakah repo public), dan "
        "tidak ada file CSV lokal. Upload lewat sidebar atau perbaiki "
        "GITHUB_CSV_URL di app1.py."
    )
    if load_errors:
        st.code("\n".join(load_errors))
    st.stop()

st.sidebar.caption(f"Data loaded from: **{sumber}** ({len(df):,} rows)")


# ============================================================
# SIDEBAR - FILTER
# ============================================================
st.sidebar.header("Filter")

prov_list = sorted(df["provinsi"].dropna().unique().tolist())
prov_selected = st.sidebar.multiselect("Province", prov_list, default=prov_list)

# Kabupaten/kota hanya dari provinsi yang dipilih
kab_list = sorted(
    df[df["provinsi"].isin(prov_selected)]["kabupaten"].dropna().unique().tolist()
)
kab_selected = st.sidebar.multiselect(
    "District/Regency", kab_list, default=kab_list,
    key=f"kab_{abs(hash(tuple(prov_selected)))}",   # reset pilihan saat provinsi berubah
)

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
mask = (
    df["provinsi"].isin(prov_selected)
    & df["kabupaten"].isin(kab_selected)
    & df["jenis_fasyankes"].isin(jenis_selected)
)
fdf = df[mask].copy()


# ============================================================
# HEADER & KPI
# ============================================================
st.title("Mapping of Health Facilities and Monitoring of Tuberculosis Service Indicators")
st.caption("Presumptive case, notification, and TB enrollment data per health facility")

# Hitung fasilitas unik pakai ID kalau ada (nama bisa kembar)
if "fasyankes_id" in fdf.columns:
    n_fasilitas = int(fdf["fasyankes_id"].nunique())
else:
    n_fasilitas = int(fdf["fasyankes_label"].nunique())

kpi_cols = st.columns(6)
kpi_defs = [
    ("Number of Facilities", n_fasilitas),
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
    if stretch(
        st.button, "Map Page",
        type="primary" if st.session_state.page == "Map" else "secondary",
    ):
        st.session_state.page = "Map"
        st.rerun()

with nav_col2:
    if stretch(
        st.button, "Data Analyst Page",
        type="primary" if st.session_state.page == "Data Analyst" else "secondary",
    ):
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

        # 1 nilai unik   -> 1 kelas
        # 2-5 nilai unik -> tiap nilai satu kelas (biner / MiniDock)
        # > 5 nilai unik -> kuantil 5 kelas
        is_discrete = False
        discrete_values = None
        bin_edges = None

        if n_unique <= 1:
            n_class = 1
            class_idx = pd.Series(0, index=vals.index)
            bin_edges = np.array([vals.min(), vals.max()])

        elif n_unique <= 5:
            is_discrete = True
            discrete_values = np.sort(vals.unique())
            n_class = len(discrete_values)
            value_to_class = {v: i for i, v in enumerate(discrete_values)}
            class_idx = vals.map(value_to_class)

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

        # Ukuran titik = ketersediaan TCM saja
        map_df["radius"] = np.where(map_df["TCM_numeric"] == 1, TCM_RADIUS, BASE_RADIUS)

        # ---- Legenda: pakai colors_hex yang SAMA dengan warna di peta ----
        legend_items = []
        if is_discrete:
            for i, v in enumerate(discrete_values):
                if variabel_col == "TCM_numeric":
                    label = "Ada" if v == 1 else "Tidak ada"
                else:
                    label = str(int(v)) if float(v).is_integer() else str(v)
                legend_items.append((label, colors_hex[i]))
        else:
            edges = np.round(bin_edges).astype(int)
            if n_class == 1:
                legend_items.append((f"{edges[0]:,} – {edges[-1]:,}", colors_hex[0]))
            else:
                for i in range(n_class):
                    legend_items.append((f"{edges[i]:,} – {edges[i + 1]:,}", colors_hex[i]))
        render_legend(legend_items)
        render_size_legend()

        # ---- Zoom & pusat peta menyesuaikan sebaran data ----
        lat_min, lat_max = map_df["Latitude"].min(), map_df["Latitude"].max()
        lon_min, lon_max = map_df["Longitude"].min(), map_df["Longitude"].max()
        span = max(lat_max - lat_min, lon_max - lon_min, 0.01)
        zoom = float(np.clip(np.log2(360 / span) - 0.5, 3, 12))

        view_state = pdk.ViewState(
            latitude=float((lat_min + lat_max) / 2),
            longitude=float((lon_min + lon_max) / 2),
            zoom=zoom,
            pitch=0,
        )

        # ---- Bersihkan NaN supaya tooltip & JSON aman ----
        tooltip_cols = [
            "jumlah_terduga", "TBC_SO", "TBC_RO", "notifikasi_TBC", "MiniDock", "enrol",
        ]
        for c in tooltip_cols:
            if c in map_df.columns:
                map_df[c] = map_df[c].fillna(0).astype(int)

        keep_cols = [
            "Latitude", "Longitude", "fasyankes", "kabupaten", "jenis_fasyankes",
            "TCM", "radius", "color_r", "color_g", "color_b",
        ] + [c for c in tooltip_cols if c in map_df.columns]
        map_df = map_df[keep_cols]

        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[Longitude, Latitude]",
            get_radius="radius",
            get_fill_color="[color_r, color_g, color_b, 190]",
            radius_min_pixels=4,
            radius_max_pixels=30,
            pickable=True,
            stroked=True,
            get_line_color=[22, 35, 46],
            line_width_min_pixels=1,
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

        stretch(
            st.pydeck_chart,
            pdk.Deck(
                layers=[layer],
                initial_view_state=view_state,
                tooltip=tooltip,
                map_style="road",
            ),
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

        if variabel_col == "TCM_numeric":
            st.info(
                "Bar chart tidak informatif untuk mWRD Availability (semua nilai 0/1). "
                "Pilih variabel lain di sidebar, atau lihat chart per kabupaten di sebelah kanan."
            )
        else:
            top_df = fdf.dropna(subset=[variabel_col]).sort_values(variabel_col, ascending=False)
            if jumlah_n is not None:
                top_df = top_df.head(jumlah_n)

            chart_height = max(500, min(len(top_df) * 25, 2000))

            fig_bar = px.bar(
                top_df, x=variabel_col, y="fasyankes_label", orientation="h",
                color="jenis_fasyankes", text=variabel_col,
                color_discrete_map=JENIS_COLOR_MAP,
                labels={variabel_col: variabel_label, "fasyankes_label": "Facility"},
            )
            fig_bar.update_layout(
                yaxis=dict(autorange="reversed"),
                height=chart_height,
                plot_bgcolor=SURFACE,
                paper_bgcolor=SURFACE,
                font=dict(family="IBM Plex Sans", color=INK),
            )
            stretch(st.plotly_chart, fig_bar)

    with c2:
        st.subheader(f"Total {variabel_label} by District/Regency")

        agg_df = fdf.groupby("kabupaten", as_index=False)[variabel_col].sum().sort_values(
            variabel_col, ascending=False
        )
        fig_kab = px.bar(
            agg_df, x="kabupaten", y=variabel_col,
            labels={variabel_col: variabel_label, "kabupaten": "District/Regency"},
        )
        fig_kab.update_traces(marker_color=TEAL)
        fig_kab.update_layout(
            height=500,
            showlegend=False,
            plot_bgcolor=SURFACE,
            paper_bgcolor=SURFACE,
            font=dict(family="IBM Plex Sans", color=INK),
        )
        stretch(st.plotly_chart, fig_kab)

    st.divider()

    st.subheader("TB Cascade Comparison (Presumptive → Notification → Enrollment)")

    cascade_labels = {
        "jumlah_terduga": "Presumptive Cases",
        "notifikasi_TBC": "TB Notifications",
        "enrol": "Total Enrollment",
    }
    cascade_cols = [c for c in cascade_labels if c in fdf.columns]

    cascade_sum = fdf[cascade_cols].sum(skipna=True).reset_index()
    cascade_sum.columns = ["Stage", "Count"]
    cascade_sum["Stage"] = cascade_sum["Stage"].map(cascade_labels)

    fig_cascade = px.funnel(cascade_sum, x="Count", y="Stage")
    fig_cascade.update_traces(marker_color=TEAL_RAMP[:len(cascade_sum)])
    fig_cascade.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(family="IBM Plex Sans", color=INK),
    )
    stretch(st.plotly_chart, fig_cascade)

    st.divider()

    st.subheader("Detailed Data")
    stretch(st.dataframe, fdf.drop(columns=["fasyankes_label"]), hide_index=True)

    csv = fdf.drop(columns=["fasyankes_label"]).to_csv(index=False).encode("utf-8")
    st.download_button("Download filtered data (CSV)", csv, "data_tb_filtered.csv", "text/csv")
