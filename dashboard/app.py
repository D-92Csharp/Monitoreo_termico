import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px
import ee
import json
from datetime import date, timedelta

st.set_page_config(page_title="Monitoreo Termico - Plantas Solares Panama", layout="wide")


@st.cache_resource
def inicializar_gee():
    try:
        info_cuenta = json.loads(st.secrets["gee_service_account"]["key_json"])
        credenciales = ee.ServiceAccountCredentials(
            info_cuenta["client_email"], key_data=st.secrets["gee_service_account"]["key_json"]
        )
        ee.Initialize(credenciales, project=info_cuenta["project_id"])
    except Exception:
        ee.Initialize(project="monitoreo-termico-solar")
    return True


@st.cache_data(ttl=86400)
def obtener_tile_sentinel2():
    try:
        inicializar_gee()
        panama = ee.Geometry.Rectangle([-83.2, 7.0, -77.0, 9.7])
        fecha_fin = date.today().isoformat()
        fecha_inicio = (date.today() - timedelta(days=90)).isoformat()

        coleccion = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(panama)
            .filterDate(fecha_inicio, fecha_fin)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            .median()
        )
        vis_params = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000}
        map_id_dict = coleccion.getMapId(vis_params)
        return map_id_dict["tile_fetcher"].url_format
    except Exception as e:
        st.sidebar.warning(f"No se pudo cargar Sentinel-2 en vivo: {e}")
        return None


# --- Cargar datos (desde CSV, generados por el pipeline de GEE/clustering) ---
@st.cache_data
def cargar_datos():
    mediciones = pd.read_csv("data/processed/mediciones_termicas.csv")
    resumen = pd.read_csv("data/processed/resumen_clustering.csv")
    return mediciones, resumen


mediciones, resumen = cargar_datos()

# --- Calcular anomalia termica anual por planta ---
pivot = mediciones.pivot_table(
    index=["id_planta", "nombre", "year"], columns="anillo", values="lst_celsius"
).reset_index()
pivot["anomalia_termica"] = pivot["0_500m"] - pivot["1000_2000m"]

# --- Unir con nivel de impacto y coordenadas (fijos por planta) ---
datos = pivot.merge(
    resumen[["id_planta", "nivel_impacto", "latitud", "longitud"]],
    on="id_planta", how="left"
)

# ============ SIDEBAR: FILTROS ============
st.sidebar.header("Filtros")

anios_disponibles = sorted(datos["year"].unique())
anio_seleccionado = st.sidebar.selectbox("Año", anios_disponibles, index=len(anios_disponibles) - 1)

niveles_disponibles = datos["nivel_impacto"].unique().tolist()
niveles_seleccionados = st.sidebar.multiselect(
    "Nivel de impacto", niveles_disponibles, default=niveles_disponibles
)

rango_anomalia = st.sidebar.slider(
    "Rango de anomalia termica (C)",
    float(datos["anomalia_termica"].min()),
    float(datos["anomalia_termica"].max()),
    (float(datos["anomalia_termica"].min()), float(datos["anomalia_termica"].max())),
)

# --- Aplicar filtros ---
datos_filtrados = datos[
    (datos["year"] == anio_seleccionado)
    & (datos["nivel_impacto"].isin(niveles_seleccionados))
    & (datos["anomalia_termica"].between(*rango_anomalia))
]

# ============ TITULO ============
st.title("Monitoreo de Factores Termicos en Zonas Adyacentes a Plantas Solares - Panama")
st.caption("Comparacion de temperatura superficial (LST) entre anillo cercano (0-500m) y anillo de referencia (1-2km)")

# ============ INDICADORES ============
col1, col2, col3, col4 = st.columns(4)
col1.metric("Plantas mostradas", len(datos_filtrados))
col2.metric("Anomalia termica promedio", f"{datos_filtrados['anomalia_termica'].mean():.3f} C" if len(datos_filtrados) else "N/A")
col3.metric("Alto impacto", int((datos_filtrados["nivel_impacto"] == "Alto impacto").sum()))
col4.metric("Ano seleccionado", anio_seleccionado)

st.divider()

# ============ MAPA + GRAFICOS ============
col_mapa, col_graficos = st.columns([1.2, 1])

with col_mapa:
    st.subheader("Mapa de plantas solares")
    colores = {"Bajo impacto": "blue", "Impacto moderado": "orange", "Alto impacto": "red"}

    mapa = folium.Map(location=[8.5, -80.5], zoom_start=7, tiles=None)

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="Mapa estandar",
    ).add_to(mapa)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics",
        name="Satelital (Esri)",
    ).add_to(mapa)

    tile_sentinel = obtener_tile_sentinel2()
    if tile_sentinel:
        folium.TileLayer(
            tiles=tile_sentinel,
            attr="Google Earth Engine - Sentinel-2 (ultimos 90 dias)",
            name="Satelital reciente (Sentinel-2)",
        ).add_to(mapa)

    for _, fila in datos_filtrados.iterrows():
        folium.CircleMarker(
            location=[fila["latitud"], fila["longitud"]],
            radius=7,
            color=colores.get(fila["nivel_impacto"], "gray"),
            fill=True,
            fill_opacity=0.8,
            popup=f"{fila['nombre']}<br>Nivel: {fila['nivel_impacto']}<br>Anomalia: {fila['anomalia_termica']:.3f} C",
        ).add_to(mapa)

    folium.LayerControl().add_to(mapa)

    st_folium(mapa, width=700, height=500)

with col_graficos:
    st.subheader("Anomalia termica por nivel de impacto")
    fig_barras = px.bar(
        datos_filtrados.groupby("nivel_impacto")["anomalia_termica"].mean().reset_index(),
        x="nivel_impacto", y="anomalia_termica",
        color="nivel_impacto", color_discrete_map=colores,
        labels={"anomalia_termica": "Anomalia termica (C)", "nivel_impacto": "Nivel"},
    )
    st.plotly_chart(fig_barras, use_container_width=True)

    st.subheader("Tendencia anual de anomalia termica")
    tendencia = datos[datos["id_planta"].isin(datos_filtrados["id_planta"])].groupby("year")["anomalia_termica"].mean().reset_index()
    fig_linea = px.line(tendencia, x="year", y="anomalia_termica", markers=True,
                         labels={"anomalia_termica": "Anomalia termica (C)", "year": "Ano"})
    st.plotly_chart(fig_linea, use_container_width=True)

st.divider()
st.subheader("Tabla de datos filtrados")
st.dataframe(datos_filtrados[["nombre", "nivel_impacto", "anomalia_termica"]].sort_values("anomalia_termica", ascending=False))

st.divider()
st.subheader("Cobertura de suelo adyacente por nivel de impacto")
st.caption("Composicion del terreno en el anillo cercano (0-500m) de cada planta, segun nivel de impacto termico. Fuente: ESA WorldCover 10m.")

composicion = pd.read_csv("data/processed/composicion_suelo_por_impacto.csv")

fig_composicion = px.bar(
    composicion,
    x="nivel_impacto",
    y=["pct_bosque", "pct_agricola", "pct_urbano", "pct_agua"],
    labels={"value": "% de cobertura", "nivel_impacto": "Nivel de impacto", "variable": "Tipo de cobertura"},
    color_discrete_map={
        "pct_bosque": "#2E7D32",
        "pct_agricola": "#F9A825",
        "pct_urbano": "#757575",
        "pct_agua": "#1976D2",
    },
    barmode="stack",
)
fig_composicion.for_each_trace(lambda t: t.update(name={
    "pct_bosque": "Bosque", "pct_agricola": "Agricola", "pct_urbano": "Urbano", "pct_agua": "Agua"
}[t.name]))
st.plotly_chart(fig_composicion, use_container_width=True)

st.caption(
    "Las plantas de bajo impacto (efecto de enfriamiento) estan predominantemente rodeadas de bosque, "
    "mientras que las de alto impacto presentan mayor proporcion de terreno agricola/desbrozado y huella urbana - "
    "consistente con la correlacion negativa entre perdida de vegetacion (NDVI) y anomalia termica (r = -0.581, p < 0.001)."
)
