"""
Dashboard TB - Fasilitas Kesehatan (2 Halaman)
================================================

Cara menjalankan:
    pip install streamlit pandas plotly pydeck

    streamlit run app1.py

Taruh folder .streamlit/config.toml sejajar dengan file ini (mengatur warna
dasar Streamlit: tombol, chip filter, dll jadi teal, bukan merah default).

SUMBER DATA
-----------
Dashboard ini akan mencoba memuat data secara berurutan:
    1. File yang diupload manual lewat sidebar (jika ada) -> prioritas tertinggi.
    2. Data dari GitHub (raw CSV) lewat variabel GITHUB_CSV_URL di bawah ini.
    3. File data.csv lokal di folder yang sama dengan app1.py (fallback terakhir).

Kolom yang diharapkan pada data.csv:
provinsi_id, provinsi, kabupaten_id, kabupaten, jenis_fasyankes, fasyankes_id,
fasyankes, jumlah_terduga, terduga_sesuai_standar, TBC_SO, TBC_RO,
notifikasi_TBC, enrol_SO, enrol_RO, enrol, Latitude, Longitude, TCM

CATATAN PERUBAHAN
------------------
Di peta (Halaman 1):
    - WARNA titik tetap mengikuti variabel yang dipilih di sidebar (mis. TBC_RO),
      dari yang paling kecil sampai paling besar (severity scale 5 tingkat).
    - UKURAN (radius) titik sekarang TIDAK lagi mengikuti besar-kecil nilai
      variabel, melainkan mengikuti ketersediaan TCM di fasyankes tersebut:
        * TCM ada  -> radius sedikit lebih besar (TCM_RADIUS)
        * TCM tidak ada / kosong -> radius normal (BASE_RADIUS)
      Nilai kedua radius ini bisa diubah lewat konstanta BASE_RADIUS dan
      TCM_RADIUS di bagian CONFIG di bawah.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import pydeck as pdk


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Dashboard TB Fasyankes",
    layout="wide"
)

GITHUB_CSV_URL = "https://raw.githubusercontent.com/Asalulzy/Dashboard_Sebaran_Fasilitas_Kesehatan_Kab_Karawang/main/data_koordinat3.csv"

# Ukuran titik peta berdasarkan ketersediaan TCM (bukan lagi berdasarkan
# besar nilai variabel). Silakan sesuaikan angkanya jika ingin selisih
# besar-kecil yang lebih terlihat.
BASE_RADIUS = 500   # radius titik tanpa TCM
TCM_RADIUS = 850     # radius titik dengan TCM (sedikit lebih besar)


# ============================================================
# DESAIN: TOKEN WARNA, TIPOGRAFI, CSS
# ============================================================

INK = "#16232E"
PAPER = "#F6F7F4"
SURFACE = "#FFFFFF"
LINE = "#DCE2DE"
TEAL = "#0B5E63"
SLATE = "#3A5A78"

# skala 5 tingkat untuk merepresentasikan JUMLAH/KEPARAHAN — dipakai
# konsisten di peta, legenda, dan (kalau relevan) grafik, supaya satu
# skema warna dipelajari sekali oleh pengguna.
SEVERITY_SCALE = ["#F2D680", "#E8A33D", "#C1642F", "#93321F", "#7A1F1B"]
SEVERITY_RGB = [
    tuple(int(h.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    for h in SEVERITY_SCALE
]


def get_severity_colors(n_class):
    """
    Ambil n_class warna dari SEVERITY_SCALE secara MERATA (dari ujung
    terang ke ujung gelap), bukan mengambil n_class warna terakhir saja.
    Ini penting supaya saat kelasnya cuma 2-3 (mis. variabel biner atau
    data dengan sedikit nilai unik), kontras warnanya tetap jelas —
    tidak keambil 2-3 warna gelap yang mirip di ujung skala.

    n_class=1 -> warna paling gelap (paling "parah") saja.
    n_class=2 -> warna paling terang & paling gelap (kontras maksimal).
    n_class=5 -> seluruh skala, seperti semula.
    """
    if n_class <= 1:
        return [SEVERITY_SCALE[-1]], [SEVERITY_RGB[-1]]
    idx = np.round(np.linspace(0, len(SEVERITY_SCALE) - 1, n_class)).astype(int)
    hex_colors = [SEVERITY_SCALE[i] for i in idx]
    rgb_colors = [SEVERITY_RGB[i] for i in idx]
    return hex_colors, rgb_colors

# warna kategori jenis fasyankes — konsisten di semua grafik
JENIS_COLOR_MAP = {
    "Puskesmas": TEAL,
    "Rumah Sakit": SLATE,
}

# ramp teal untuk funnel kaskade (bukan severity — ini tahapan, bukan intensitas spasial)
TEAL_RAMP = ["#CFE8E6", "#8FC6C2", "#4FA39D", "#0B5E63", "#063D40"]

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@500;600&display=swap');

html, body, [class*="css"] {{
    font-family: 'IBM Plex Sans', sans-serif;
    color: {INK};
}}
.stApp {{ background-color: {PAPER}; }}

h1 {{
    font-family: 'IBM Plex Sans', sans-serif;
    font-weight: 600;
    font-size: 2rem;
    letter-spacing: -0.01em;
    color: {INK};
    border-top: 4px solid {TEAL};
    padding-top: 0.6rem;
    margin-bottom: 0.15rem;
}}
h2, h3 {{ font-family: 'IBM Plex Sans', sans-serif; font-weight: 600; color: {INK}; }}

section[data-testid="stSidebar"] {{
    background-color: {SURFACE};
    border-right: 1px solid {LINE};
}}

hr {{ border-top: 1px solid {LINE}; }}

.stButton>button {{
    border-radius: 4px;
    font-weight: 500;
    border: 1px solid {LINE};
}}

div[data-baseweb="tag"] {{
    background-color: {TEAL} !important;
    border-radius: 4px !important;
}}

.kpi-card {{
    background-color: {SURFACE};
    border: 1px solid {LINE};
    border-top: 3px solid {TEAL};
    padding: 0.7rem 0.9rem;
    height: 100%;
}}
.kpi-label {{ font-size: 0.78rem; color: {INK}99; margin-bottom: 0.25rem; }}
.kpi-value {{
    font-family: 'IBM Plex Mono', monospace;
    font-weight: 600;
    font-size: 1.5rem;
    color: {INK};
}}

.legend-row {{ display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.4rem 0 1rem 0; }}
.legend-chip {{
    display: flex; align-items: center; gap: 0.35rem;
    font-size: 0.78rem; color: {INK}CC;
    border: 1px solid {LINE}; padding: 0.2rem 0.55rem;
    background-color: {SURFACE};
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
    """Legenda kecil untuk menjelaskan bahwa ukuran titik = ketersediaan TCM."""
    st.markdown(
        f"""<div class="legend-row">
                <div class="legend-chip">
                    <span class="legend-swatch-round" style="width:8px;height:8px;"></span>
                    Tanpa TCM (ukuran normal)
                </div>
                <div class="legend-chip">
                    <span class="legend-swatch-round" style="width:14px;height:14px;"></span>
                    Ada TCM (ukuran sedikit lebih besar)
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

    numeric_cols = [
        "jumlah_terduga", "terduga_sesuai_standar", "TBC_SO", "TBC_RO",
        "notifikasi_TBC", "enrol_SO", "enrol_RO", "enrol", "Latitude", "Longitude"
    ]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

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
        return load_data(uploaded_file), "upload manual"

    if GITHUB_CSV_URL.strip() != "":
        try:
            return load_data(GITHUB_CSV_URL), "GitHub"
        except Exception as e:
            st.sidebar.warning(f"Gagal memuat data dari GitHub ({e}). Mencoba file lokal data.csv...")

    try:
        return load_data("data.csv"), "file lokal"
    except FileNotFoundError:
        return None, None


# ============================================================
# SIDEBAR - SUMBER DATA
# ============================================================

st.sidebar.header("Sumber Data")

uploaded = st.sidebar.file_uploader(
    "Upload data.csv (opsional, override sumber otomatis)", type="csv"
)

df, sumber = load_data_with_fallback(uploaded)

if df is None:
    st.error(
        "Data tidak ditemukan. Tidak ada file upload, link GitHub belum diisi "
        "(GITHUB_CSV_URL), dan data.csv lokal tidak ditemukan. Silakan upload "
        "lewat sidebar atau isi GITHUB_CSV_URL di app1.py."
    )
    st.stop()

st.sidebar.caption(f"Data dimuat dari: **{sumber}**")


# ============================================================
# SIDEBAR - FILTER
# ============================================================

st.sidebar.header("Filter")

kab_list = sorted(df["kabupaten"].dropna().unique().tolist())
kab_selected = st.sidebar.multiselect("Kabupaten", kab_list, default=kab_list)

jenis_list = sorted(df["jenis_fasyankes"].dropna().unique().tolist())
jenis_selected = st.sidebar.multiselect("Jenis Fasyankes", jenis_list, default=jenis_list)


# ============================================================
# VARIABEL UNTUK PETA & GRAFIK
# ============================================================

variabel_options = {
    "Jumlah Terduga TB": "jumlah_terduga",
    "Terduga Sesuai Standar": "terduga_sesuai_standar",
    "TBC Sensitif Obat (SO)": "TBC_SO",
    "TBC Resisten Obat (RO)": "TBC_RO",
    "Notifikasi TBC": "notifikasi_TBC",
    "Enrolment SO": "enrol_SO",
    "Enrolment RO": "enrol_RO",
    "Total Enrolment": "enrol",
    "Ketersediaan TCM": "TCM_numeric",
}

variabel_label = st.sidebar.selectbox("Variabel untuk peta & grafik", list(variabel_options.keys()))
variabel_col = variabel_options[variabel_label]


# ============================================================
# APPLY FILTER (tanpa filter TCM — faskes non-TCM/kosong tetap masuk)
# ============================================================

mask = df["kabupaten"].isin(kab_selected) & df["jenis_fasyankes"].isin(jenis_selected)
fdf = df[mask].copy()


# ============================================================
# HEADER & KPI
# ============================================================

st.title("Pemetaan Fasilitas Kesehatan dan Pemantauan Indikator Layanan Tuberkulosis")
st.caption("Data terduga, notifikasi, dan enrolment TB per fasyankes")

kpi_cols = st.columns(6)
kpi_defs = [
    ("Jumlah Fasyankes", fdf["fasyankes"].nunique()),
    ("Total Terduga", int(fdf["jumlah_terduga"].sum(skipna=True))),
    ("Terduga Sesuai Standar", int(fdf["terduga_sesuai_standar"].sum(skipna=True))),
    ("TBC SO", int(fdf["TBC_SO"].sum(skipna=True))),
    ("TBC RO", int(fdf["TBC_RO"].sum(skipna=True))),
    ("Notifikasi TBC", int(fdf["notifikasi_TBC"].sum(skipna=True))),
]
for col, (label, value) in zip(kpi_cols, kpi_defs):
    kpi_card(label, value, col)

st.divider()


# ============================================================
# NAVIGASI HALAMAN
# ============================================================

if "page" not in st.session_state:
    st.session_state.page = "Peta"

nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 4])

with nav_col1:
    if st.button("Halaman Peta",
                  type="primary" if st.session_state.page == "Peta" else "secondary",
                  use_container_width=True):
        st.session_state.page = "Peta"
        st.rerun()

with nav_col2:
    if st.button("Halaman Data Analyst",
                  type="primary" if st.session_state.page == "Data Analyst" else "secondary",
                  use_container_width=True):
        st.session_state.page = "Data Analyst"
        st.rerun()

st.divider()


# ============================================================
# HALAMAN 1: PETA
# ============================================================

if st.session_state.page == "Peta":

    st.subheader(f"Peta Sebaran: {variabel_label}")
    st.caption("Warna titik mengikuti nilai variabel di atas · Ukuran titik menunjukkan ketersediaan TCM")

    map_df = fdf.dropna(subset=["Latitude", "Longitude", variabel_col]).copy()

    if map_df.empty:
        st.info("Tidak ada data untuk ditampilkan pada peta dengan filter saat ini.")

    else:
        # ------------------------------------------------------
        # Kelas warna: 5 kelas berbasis kuantil data yang tampil,
        # dipetakan ke SEVERITY_SCALE. Kalau data terlalu sedikit
        # / nilainya seragam, turunkan jumlah kelas otomatis.
        # ------------------------------------------------------
        vals = map_df[variabel_col]
        n_unique = vals.nunique()

        # ------------------------------------------------------
        # Penentuan kelas warna:
        #   - 1 nilai unik saja       -> 1 kelas (semua titik sama)
        #   - 2-5 nilai unik (mis.    -> tiap nilai unik jadi kelasnya sendiri,
        #     biner 0/1 seperti          jadi variabel biner TETAP dapat 2 kelas
        #     Ketersediaan TCM)          warna berbeda, bukan collapse ke 1.
        #   - > 5 nilai unik          -> kuantil 5 kelas seperti sebelumnya.
        # ------------------------------------------------------
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
                classed, bin_edges = pd.qcut(
                    vals, q=5, retbins=True, duplicates="drop"
                )
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

        # ------------------------------------------------------
        # Ukuran titik: TIDAK lagi mengikuti besar nilai variabel.
        # Sekarang murni berdasarkan ketersediaan TCM di fasyankes:
        #   TCM ada       -> TCM_RADIUS (sedikit lebih besar)
        #   TCM tidak ada -> BASE_RADIUS (ukuran normal)
        # ------------------------------------------------------
        map_df["radius"] = np.where(
            map_df["TCM_numeric"] == 1, TCM_RADIUS, BASE_RADIUS
        )

        # ------------------------------------------------------
        # Legenda: chip warna (nilai variabel) + chip ukuran (TCM)
        # ------------------------------------------------------
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
            pitch=0
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
            auto_highlight=True
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
                    {{kabupaten}} &middot; {{jenis_fasyankes}} &middot; TCM: {{TCM}}
                </div>
                <table style="width:100%; border-collapse:collapse; font-size:12px;
                               font-family:'IBM Plex Mono',monospace;">
                    <tr><td style="color:#5b6b73;">Jumlah Terduga</td>
                        <td style="text-align:right; font-weight:600;">{{jumlah_terduga}}</td></tr>
                    <tr><td style="color:#5b6b73;">Sesuai Standar</td>
                        <td style="text-align:right; font-weight:600;">{{terduga_sesuai_standar}}</td></tr>
                    <tr><td style="color:#5b6b73;">TBC SO</td>
                        <td style="text-align:right; font-weight:600;">{{TBC_SO}}</td></tr>
                    <tr><td style="color:#5b6b73;">TBC RO</td>
                        <td style="text-align:right; font-weight:600;">{{TBC_RO}}</td></tr>
                    <tr><td style="color:#5b6b73;">Notifikasi TBC</td>
                        <td style="text-align:right; font-weight:600;">{{notifikasi_TBC}}</td></tr>
                    <tr style="border-top:1px solid {LINE};">
                        <td style="color:#5b6b73;">Total Enrolment</td>
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
            }
        }

        st.pydeck_chart(
            pdk.Deck(layers=[layer], initial_view_state=view_state, tooltip=tooltip, map_style="road"),
            use_container_width=True,
            height=820
        )


# ============================================================
# HALAMAN 2: DATA ANALYST
# ============================================================

else:

    st.subheader("Pengaturan Tampilan")

    jumlah_options = {"Top 10": 10, "Top 15": 15, "Top 50": 50, "Tampilkan Semua": None}
    jumlah_label = st.selectbox(
        "Jumlah data yang ditampilkan (grafik Top Fasyankes)",
        list(jumlah_options.keys()), index=1
    )
    jumlah_n = jumlah_options[jumlah_label]

    st.divider()

    c1, c2 = st.columns(2)

    with c1:
        judul_top = (
            f"{jumlah_label} Fasyankes - {variabel_label}"
            if jumlah_n is not None else f"Semua Fasyankes - {variabel_label}"
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
        st.subheader(f"Total {variabel_label} per Kabupaten")

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

    st.subheader("Perbandingan Kaskade TB (Terduga → Notifikasi → Enrolment)")

    cascade_cols = ["jumlah_terduga", "terduga_sesuai_standar", "notifikasi_TBC", "enrol"]
    cascade_cols = [c for c in cascade_cols if c in fdf.columns]

    cascade_sum = fdf[cascade_cols].sum(skipna=True).reset_index()
    cascade_sum.columns = ["Tahap", "Jumlah"]

    fig_cascade = px.funnel(cascade_sum, x="Jumlah", y="Tahap")
    fig_cascade.update_traces(marker_color=TEAL_RAMP[:len(cascade_sum)])
    fig_cascade.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(family="IBM Plex Sans", color=INK),
    )
    st.plotly_chart(fig_cascade, use_container_width=True)

    st.divider()

    st.subheader("Data Detail")
    st.dataframe(fdf, use_container_width=True, hide_index=True)

    csv = fdf.to_csv(index=False).encode("utf-8")
    st.download_button("Download data terfilter (CSV)", csv, "data_tb_filtered.csv", "text/csv")
