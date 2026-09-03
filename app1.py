"""
Dashboard TB - Fasilitas Kesehatan (2 Halaman)
================================================

Cara menjalankan:
    pip install streamlit pandas plotly pydeck

    streamlit run app.py

SUMBER DATA
-----------
Dashboard ini akan mencoba memuat data secara berurutan:
    1. File yang diupload manual lewat sidebar (jika ada) -> prioritas tertinggi,
       berguna kalau sewaktu-waktu mau ganti data tanpa push ke GitHub.
    2. Data dari GitHub (raw CSV) lewat variabel GITHUB_CSV_URL di bawah ini.
       -> Ganti nilainya dengan link RAW file data.csv kamu di GitHub, contoh:
          "https://raw.githubusercontent.com/USERNAME/REPO/main/data.csv"
    3. File data.csv lokal di folder yang sama dengan app.py (fallback terakhir).

Kolom yang diharapkan pada data.csv:
provinsi_id, provinsi, kabupaten_id, kabupaten, jenis_fasyankes, fasyankes_id,
fasyankes, jumlah_terduga, terduga_sesuai_standar, TBC_SO, TBC_RO,
notifikasi_TBC, enrol_SO, enrol_RO, enrol, Latitude, Longitude, TCM
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import pydeck as pdk


# ============================================================
# CONFIG
# ============================================================

st.set_page_config(
    page_title="Dashboard TB Fasyankes",
    layout="wide"
)

# GANTI dengan link RAW CSV kamu di GitHub agar data otomatis termuat
# tanpa perlu upload setiap login. Kosongkan ("") jika belum ada.
GITHUB_CSV_URL = ""


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data
def load_data(path_or_url_or_buffer):

    df = pd.read_csv(path_or_url_or_buffer)

    # Bersihkan nama kolom
    df.columns = [c.strip() for c in df.columns]

    # Pastikan tipe numerik
    numeric_cols = [
        "jumlah_terduga",
        "terduga_sesuai_standar",
        "TBC_SO",
        "TBC_RO",
        "notifikasi_TBC",
        "enrol_SO",
        "enrol_RO",
        "enrol",
        "Latitude",
        "Longitude"
    ]

    for c in numeric_cols:

        if c in df.columns:

            df[c] = pd.to_numeric(
                df[c],
                errors="coerce"
            )

    # --------------------------------------------------------
    # Siapkan versi numerik dari kolom TCM agar bisa dipakai
    # sebagai variabel di peta & grafik (mis. Ya/Tidak, Ada/Kosong,
    # atau sudah berupa angka 0/1).
    # --------------------------------------------------------

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
    """
    Urutan prioritas:
    1. File upload manual (sidebar)
    2. Link GitHub (GITHUB_CSV_URL)
    3. File data.csv lokal
    """

    if uploaded_file is not None:
        return load_data(uploaded_file), "upload manual"

    if GITHUB_CSV_URL.strip() != "":

        try:

            return load_data(GITHUB_CSV_URL), "GitHub"

        except Exception as e:

            st.sidebar.warning(
                f"Gagal memuat data dari GitHub ({e}). "
                "Mencoba file lokal data.csv..."
            )

    try:

        return load_data("data.csv"), "file lokal"

    except FileNotFoundError:

        return None, None


# ============================================================
# SIDEBAR - SUMBER DATA
# ============================================================

st.sidebar.header("Sumber Data")

uploaded = st.sidebar.file_uploader(
    "Upload data.csv (opsional, override sumber otomatis)",
    type="csv"
)

df, sumber = load_data_with_fallback(uploaded)

if df is None:

    st.error(
        "Data tidak ditemukan. Tidak ada file upload, "
        "link GitHub belum diisi (GITHUB_CSV_URL), dan "
        "data.csv lokal tidak ditemukan. "
        "Silakan upload lewat sidebar atau isi GITHUB_CSV_URL di app.py."
    )

    st.stop()

st.sidebar.caption(f"Data dimuat dari: **{sumber}**")


# ============================================================
# SIDEBAR - FILTER
# ============================================================

st.sidebar.header("Filter")


# ------------------------------------------------------------
# FILTER KABUPATEN
# ------------------------------------------------------------

kab_list = sorted(
    df["kabupaten"]
    .dropna()
    .unique()
    .tolist()
)

kab_selected = st.sidebar.multiselect(
    "Kabupaten",
    kab_list,
    default=kab_list
)


# ------------------------------------------------------------
# FILTER JENIS FASYANKES
# ------------------------------------------------------------

jenis_list = sorted(
    df["jenis_fasyankes"]
    .dropna()
    .unique()
    .tolist()
)

jenis_selected = st.sidebar.multiselect(
    "Jenis Fasyankes",
    jenis_list,
    default=jenis_list
)


# ============================================================
# VARIABEL UNTUK PETA & GRAFIK
# ============================================================

variabel_options = {

    "Jumlah Terduga TB":
        "jumlah_terduga",

    "Terduga Sesuai Standar":
        "terduga_sesuai_standar",

    "TBC Sensitif Obat (SO)":
        "TBC_SO",

    "TBC Resisten Obat (RO)":
        "TBC_RO",

    "Notifikasi TBC":
        "notifikasi_TBC",

    "Enrolment SO":
        "enrol_SO",

    "Enrolment RO":
        "enrol_RO",

    "Total Enrolment":
        "enrol",

    "Ketersediaan TCM":
        "TCM_numeric",
}


variabel_label = st.sidebar.selectbox(
    "Variabel untuk peta & grafik",
    list(variabel_options.keys())
)

variabel_col = variabel_options[
    variabel_label
]


# ============================================================
# APPLY FILTER
# ============================================================

# HANYA filter berdasarkan:
# 1. Kabupaten
# 2. Jenis Fasyankes
#
# TIDAK ADA FILTER TCM
#
# Dengan demikian:
# - Faskes TCM tetap masuk
# - Faskes non-TCM tetap masuk
# - Faskes dengan TCM kosong/NaN tetap masuk

mask = (
    df["kabupaten"].isin(kab_selected)
    &
    df["jenis_fasyankes"].isin(jenis_selected)
)

fdf = df[mask].copy()


# ============================================================
# HEADER & KPI
# ============================================================

st.title(
    "Pemetaan Fasilitas Kesehatan dan Pemantauan Indikator Layanan Tuberkulosis"
)

st.caption(
    "Data terduga, notifikasi, dan enrolment TB per fasyankes"
)


# ------------------------------------------------------------
# KPI
# ------------------------------------------------------------

kpi_cols = st.columns(6)

kpi_defs = [

    (
        "Jumlah Fasyankes",
        fdf["fasyankes"].nunique()
    ),

    (
        "Total Terduga",
        int(
            fdf["jumlah_terduga"]
            .sum(skipna=True)
        )
    ),

    (
        "Terduga Sesuai Standar",
        int(
            fdf["terduga_sesuai_standar"]
            .sum(skipna=True)
        )
    ),

    (
        "TBC SO",
        int(
            fdf["TBC_SO"]
            .sum(skipna=True)
        )
    ),

    (
        "TBC RO",
        int(
            fdf["TBC_RO"]
            .sum(skipna=True)
        )
    ),

    (
        "Notifikasi TBC",
        int(
            fdf["notifikasi_TBC"]
            .sum(skipna=True)
        )
    ),
]


for col, (label, value) in zip(
    kpi_cols,
    kpi_defs
):

    col.metric(
        label,
        f"{value:,}"
    )


st.divider()


# ============================================================
# NAVIGASI HALAMAN (tepat di bawah KPI)
# ============================================================

if "page" not in st.session_state:
    st.session_state.page = "Peta"

nav_col1, nav_col2, nav_col3 = st.columns([1, 1, 4])

with nav_col1:

    if st.button(
        "Halaman Peta",
        type="primary" if st.session_state.page == "Peta" else "secondary",
        use_container_width=True
    ):
        st.session_state.page = "Peta"
        st.rerun()

with nav_col2:

    if st.button(
        "Halaman Data Analyst",
        type="primary" if st.session_state.page == "Data Analyst" else "secondary",
        use_container_width=True
    ):
        st.session_state.page = "Data Analyst"
        st.rerun()

st.divider()


# ============================================================
# HALAMAN 1: PETA (full frame, tampilan besar)
# ============================================================

if st.session_state.page == "Peta":

    st.subheader(
        f"Peta Sebaran: {variabel_label}"
    )

    map_df = fdf.dropna(
        subset=[
            "Latitude",
            "Longitude",
            variabel_col
        ]
    ).copy()

    if map_df.empty:

        st.info(
            "Tidak ada data untuk ditampilkan "
            "pada peta dengan filter saat ini."
        )

    else:

        # ----------------------------------------------------
        # Radius titik
        # ----------------------------------------------------

        max_val = map_df[
            variabel_col
        ].max()

        if pd.isna(max_val) or max_val <= 0:

            max_val = 1

        map_df["radius"] = (
            300
            +
            (
                map_df[variabel_col]
                / max_val
            )
            * 2500
        )

        # ----------------------------------------------------
        # Warna titik
        # ----------------------------------------------------

        map_df["color_r"] = 255

        map_df["color_g"] = (
            255
            -
            (
                map_df[variabel_col]
                / max_val
            )
            * 200
        ).clip(
            0,
            255
        ).astype(int)

        map_df["color_b"] = 60

        # ----------------------------------------------------
        # View state
        # ----------------------------------------------------

        view_state = pdk.ViewState(

            latitude=map_df[
                "Latitude"
            ].mean(),

            longitude=map_df[
                "Longitude"
            ].mean(),

            zoom=9,

            pitch=0
        )

        # ======================================================
        # MAP LAYER
        # ======================================================

        layer = pdk.Layer(

            "ScatterplotLayer",

            data=map_df,

            get_position="[Longitude, Latitude]",

            get_radius="radius",

            get_fill_color=(
                "[color_r, color_g, color_b, 180]"
            ),

            pickable=True,

            stroked=True,

            get_line_color=[
                80,
                0,
                0
            ],

            auto_highlight=True
        )

        # ======================================================
        # TOOLTIP
        # ======================================================

        tooltip = {

            "html": """

            <div style="
                font-family: Arial, sans-serif;
                min-width: 300px;
                max-width: 380px;
                line-height: 1.5;
            ">

                <div style="
                    font-size: 17px;
                    font-weight: bold;
                    margin-bottom: 8px;
                ">
                    {fasyankes}
                </div>


                <div style="
                    border-bottom: 1px solid #ddd;
                    padding-bottom: 8px;
                    margin-bottom: 8px;
                ">

                    <b>Kabupaten:</b>
                    {kabupaten}<br/>

                    <b>Jenis Fasyankes:</b>
                    {jenis_fasyankes}<br/>

                    <b>TCM:</b>
                    {TCM}

                </div>


                <div style="
                    font-size: 14px;
                    font-weight: bold;
                    margin-bottom: 5px;
                ">
                    Indikator TB
                </div>


                <table style="
                    width: 100%;
                    border-collapse: collapse;
                ">

                    <tr>
                        <td>Jumlah Terduga</td>
                        <td style="text-align:right;">
                            <b>{jumlah_terduga}</b>
                        </td>
                    </tr>

                    <tr>
                        <td>Terduga Sesuai Standar</td>
                        <td style="text-align:right;">
                            <b>{terduga_sesuai_standar}</b>
                        </td>
                    </tr>

                    <tr>
                        <td>TBC SO</td>
                        <td style="text-align:right;">
                            <b>{TBC_SO}</b>
                        </td>
                    </tr>

                    <tr>
                        <td>TBC RO</td>
                        <td style="text-align:right;">
                            <b>{TBC_RO}</b>
                        </td>
                    </tr>

                    <tr>
                        <td>Notifikasi TBC</td>
                        <td style="text-align:right;">
                            <b>{notifikasi_TBC}</b>
                        </td>
                    </tr>

                    <tr>
                        <td>Enrolment SO</td>
                        <td style="text-align:right;">
                            <b>{enrol_SO}</b>
                        </td>
                    </tr>

                    <tr>
                        <td>Enrolment RO</td>
                        <td style="text-align:right;">
                            <b>{enrol_RO}</b>
                        </td>
                    </tr>

                    <tr style="
                        border-top: 1px solid #ccc;
                    ">

                        <td>
                            <b>Total Enrolment</b>
                        </td>

                        <td style="text-align:right;">
                            <b>{enrol}</b>
                        </td>

                    </tr>

                </table>


                <div style="
                    margin-top: 8px;
                    padding-top: 8px;
                    border-top: 1px solid #ddd;
                    color: #555;
                ">

                    <b>Koordinat</b><br/>

                    Latitude:
                    {Latitude}<br/>

                    Longitude:
                    {Longitude}

                </div>

            </div>

            """,

            "style": {
                "backgroundColor": "white",
                "color": "black",
                "border": "1px solid #ccc",
                "borderRadius": "8px",
                "padding": "10px"
            }
        }

        # ------------------------------------------------------
        # DISPLAY MAP - ukuran besar, satu frame layar
        # ------------------------------------------------------

        st.pydeck_chart(

            pdk.Deck(

                layers=[layer],

                initial_view_state=view_state,

                tooltip=tooltip,

                map_style="road"
            ),

            use_container_width=True,

            height=820
        )


# ============================================================
# HALAMAN 2: DATA ANALYST
# ============================================================

else:

    # --------------------------------------------------------
    # SETTING JUMLAH DATA YANG DITAMPILKAN
    # --------------------------------------------------------

    st.subheader("Pengaturan Tampilan")

    jumlah_options = {
        "Top 10": 10,
        "Top 15": 15,
        "Top 50": 50,
        "Tampilkan Semua": None,
    }

    jumlah_label = st.selectbox(
        "Jumlah data yang ditampilkan (grafik Top Fasyankes)",
        list(jumlah_options.keys()),
        index=1  # default Top 15
    )

    jumlah_n = jumlah_options[jumlah_label]

    st.divider()

    # --------------------------------------------------------
    # GRAFIK
    # --------------------------------------------------------

    c1, c2 = st.columns(2)

    # ----------------------------------------------------------
    # TOP N FASYANKES
    # ----------------------------------------------------------

    with c1:

        judul_top = (
            f"{jumlah_label} Fasyankes - {variabel_label}"
            if jumlah_n is not None
            else f"Semua Fasyankes - {variabel_label}"
        )

        st.subheader(judul_top)

        top_df = (
            fdf
            .dropna(
                subset=[variabel_col]
            )
            .sort_values(
                variabel_col,
                ascending=False
            )
        )

        if jumlah_n is not None:
            top_df = top_df.head(jumlah_n)

        chart_height = max(
            500,
            min(
                len(top_df) * 25,
                2000
            )
        )

        fig_bar = px.bar(

            top_df,

            x=variabel_col,

            y="fasyankes",

            orientation="h",

            color="jenis_fasyankes",

            text=variabel_col
        )

        fig_bar.update_layout(

            yaxis=dict(
                autorange="reversed"
            ),

            height=chart_height
        )

        st.plotly_chart(
            fig_bar,
            use_container_width=True
        )

    # ----------------------------------------------------------
    # TOTAL PER KABUPATEN
    # ----------------------------------------------------------

    with c2:

        st.subheader(
            f"Total {variabel_label} per Kabupaten"
        )

        agg_df = (

            fdf
            .groupby(
                "kabupaten",
                as_index=False
            )[variabel_col]
            .sum()
            .sort_values(
                variabel_col,
                ascending=False
            )
        )

        fig_kab = px.bar(

            agg_df,

            x="kabupaten",

            y=variabel_col,

            color="kabupaten"
        )

        fig_kab.update_layout(

            height=500,

            showlegend=False
        )

        st.plotly_chart(
            fig_kab,
            use_container_width=True
        )

    st.divider()

    # --------------------------------------------------------
    # PERBANDINGAN VARIABEL
    # --------------------------------------------------------

    st.subheader(
        "Perbandingan Kaskade TB "
        "(Terduga → Notifikasi → Enrolment)"
    )

    cascade_cols = [

        "jumlah_terduga",

        "terduga_sesuai_standar",

        "notifikasi_TBC",

        "enrol"
    ]

    cascade_cols = [

        c
        for c in cascade_cols
        if c in fdf.columns

    ]

    cascade_sum = (

        fdf[cascade_cols]

        .sum(
            skipna=True
        )

        .reset_index()
    )

    cascade_sum.columns = [
        "Tahap",
        "Jumlah"
    ]

    fig_cascade = px.funnel(

        cascade_sum,

        x="Jumlah",

        y="Tahap"
    )

    st.plotly_chart(

        fig_cascade,

        use_container_width=True
    )

    st.divider()

    # --------------------------------------------------------
    # TABEL DATA
    # --------------------------------------------------------

    st.subheader(
        "Data Detail"
    )

    st.dataframe(

        fdf,

        use_container_width=True,

        hide_index=True
    )

    # --------------------------------------------------------
    # DOWNLOAD
    # --------------------------------------------------------

    csv = fdf.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(

        "Download data terfilter (CSV)",

        csv,

        "data_tb_filtered.csv",

        "text/csv"
    )