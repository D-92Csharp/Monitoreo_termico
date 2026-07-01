import sqlite3
import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px

st.set_page_config(page_title="Monitoreo Térmico - Plantas Solares Panamá", layout="wide")

# --- Cargar datos ---
@st.cache_data
def cargar_datos():
    conn = sqlite3.connect("data/processed/monitoreo_termico.db")
    mediciones = pd.read_sql("SELECT * FROM mediciones_termicas", conn)
    resumen = pd.read_sql("SELECT * FROM resumen_clustering", conn)
    conn.close()
    return mediciones, resumen

mediciones, resumen = cargar_datos()

# --- Calcular anomalía térmica anual por planta ---
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
    "Rango de anomalía térmica (°C)",
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

# ============ TÍTULO ============
st.title("🌡️ Monitoreo de Factores Térmicos en Zonas Adyacentes a Plantas Solares — Panamá")
st.caption("Comparación de temperatura superficial (LST) entre anillo cercano (0-500m) y anillo de referencia (1-2km)")

# ============ INDICADORES ============
col1, col2, col3, col4 = st.columns(4)
col1.metric("Plantas mostradas", len(datos_filtrados))
col2.metric("Anomalía térmica promedio", f"{datos_filtrados['anomalia_termica'].mean():.3f} °C" if len(datos_filtrados) else "N/A")
col3.metric("Alto impacto", int((datos_filtrados["nivel_impacto"] == "Alto impacto").sum()))
col4.metric("Año seleccionado", anio_seleccionado)

st.divider()

# ============ MAPA + GRÁFICOS ============
col_mapa, col_graficos = st.columns([1.2, 1])

with col_mapa:
    st.subheader("Mapa de plantas solares")
    colores = {"Bajo impacto": "blue", "Impacto moderado": "orange", "Alto impacto": "red"}

    mapa = folium.Map(location=[8.5, -80.5], zoom_start=7)
    for _, fila in datos_filtrados.iterrows():
        folium.CircleMarker(
            location=[fila["latitud"], fila["longitud"]],
            radius=7,
            color=colores.get(fila["nivel_impacto"], "gray"),
            fill=True,
            fill_opacity=0.8,
            popup=f"{fila['nombre']}<br>Nivel: {fila['nivel_impacto']}<br>Anomalía: {fila['anomalia_termica']:.3f} °C",
        ).add_to(mapa)

    st_folium(mapa, width=700, height=500)

with col_graficos:
    st.subheader("Anomalía térmica por nivel de impacto")
    fig_barras = px.bar(
        datos_filtrados.groupby("nivel_impacto")["anomalia_termica"].mean().reset_index(),
        x="nivel_impacto", y="anomalia_termica",
        color="nivel_impacto", color_discrete_map=colores,
        labels={"anomalia_termica": "Anomalía térmica (°C)", "nivel_impacto": "Nivel"},
    )
    st.plotly_chart(fig_barras, use_container_width=True)

    st.subheader("Tendencia anual de anomalía térmica")
    tendencia = datos[datos["id_planta"].isin(datos_filtrados["id_planta"])].groupby("year")["anomalia_termica"].mean().reset_index()
    fig_linea = px.line(tendencia, x="year", y="anomalia_termica", markers=True,
                         labels={"anomalia_termica": "Anomalía térmica (°C)", "year": "Año"})
    st.plotly_chart(fig_linea, use_container_width=True)

st.divider()
st.subheader("Tabla de datos filtrados")
st.dataframe(datos_filtrados[["nombre", "nivel_impacto", "anomalia_termica"]].sort_values("anomalia_termica", ascending=False))
