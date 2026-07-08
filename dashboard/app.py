import pandas as pd
import numpy as np
import streamlit as st
import folium
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
import ee
import json
from datetime import date, timedelta

st.set_page_config(page_title="Monitoreo Térmico - Plantas Solares Panamá", layout="wide")


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
def obtener_tile_sentinel2_reciente():
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
        st.sidebar.warning(f"No se pudo cargar Sentinel-2 reciente: {type(e).__name__}: {e}")
        return None


@st.cache_data(ttl=86400)
def obtener_tile_sentinel2_por_anio(anio):
    try:
        inicializar_gee()
        panama = ee.Geometry.Rectangle([-83.2, 7.0, -77.0, 9.7])
        fecha_inicio = f"{anio}-01-01"
        fecha_fin = f"{anio}-12-31"

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
        st.sidebar.warning(f"No se pudo cargar Sentinel-2 de {anio}: {type(e).__name__}: {e}")
        return None


ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_ATTR = "Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics"

COLORES = {"Bajo impacto": "blue", "Impacto moderado": "orange", "Alto impacto": "red"}
COLORES_COBERTURA = {"Bosque": "#2E7D32", "Agrícola": "#F9A825", "Urbano": "#757575", "Agua": "#1976D2"}


def agregar_capas_base(mapa, tile_satelital, nombre_capa_satelital):
    folium.TileLayer(tiles="OpenStreetMap", name="Mapa estándar").add_to(mapa)
    folium.TileLayer(tiles=ESRI_URL, attr=ESRI_ATTR, name="Satelital (Esri)").add_to(mapa)
    if tile_satelital:
        folium.TileLayer(
            tiles=tile_satelital,
            attr="Google Earth Engine - Sentinel-2",
            name=nombre_capa_satelital,
        ).add_to(mapa)


# --- Cargar datos ---
@st.cache_data
def cargar_datos():
    mediciones = pd.read_csv("data/processed/mediciones_termicas.csv")
    resumen = pd.read_csv("data/processed/resumen_clustering.csv")
    correlacion = pd.read_csv("data/processed/correlacion_ndvi_temperatura.csv")
    composicion = pd.read_csv("data/processed/composicion_suelo_por_impacto.csv")
    impacto_eco = pd.read_csv("data/processed/impacto_ecosistemas_adyacentes.csv")
    return mediciones, resumen, correlacion, composicion, impacto_eco


mediciones, resumen, correlacion, composicion, impacto_eco = cargar_datos()

# --- Calcular anomalía térmica y temperatura del punto, por planta y año ---
pivot = mediciones.pivot_table(
    index=["id_planta", "nombre", "year"], columns="anillo", values="lst_celsius"
).reset_index()
pivot["anomalia_termica"] = pivot["0_500m"] - pivot["1000_2000m"]
pivot = pivot.rename(columns={"0_500m": "temperatura_planta"})

datos = pivot.merge(
    resumen[["id_planta", "nivel_impacto", "latitud", "longitud"]],
    on="id_planta", how="left"
)

tile_reciente = obtener_tile_sentinel2_reciente()

# ============ TÍTULO ============
st.title("Monitoreo de Factores Térmicos en Zonas Adyacentes a Plantas Solares - Panamá")
st.caption("Comparación de temperatura superficial (LST) entre anillo cercano (0-500m) y anillo de referencia (1-2km)")

tab_resumen, tab_mapa, tab_ndvi, tab_planta, tab_comparacion, tab_acerca = st.tabs([
    "Resumen",
    "Mapa y Anomalía Térmica",
    "NDVI y Cobertura de Suelo",
    "Planta Individual",
    "Comparación Año vs Año",
    "Acerca del Proyecto",
])

# ============ TAB: RESUMEN ============
with tab_resumen:
    r_valor = np.corrcoef(correlacion["anomalia_ndvi"], correlacion["anomalia_termica"])[0, 1]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Plantas analizadas", resumen["id_planta"].nunique())
    col2.metric("Anomalía térmica promedio", f"{resumen['anomalia_termica_promedio'].mean():.3f} °C")
    col3.metric("Alto impacto", int((resumen["nivel_impacto"] == "Alto impacto").sum()))
    col4.metric("Correlación NDVI-Temperatura", f"{r_valor:.3f}", help="p < 0.0001 (altamente significativo)")

    st.divider()
    st.subheader("Hallazgos principales")
    st.markdown(
        "- **28 de 49 plantas (57%)** muestran anomalía térmica positiva (efecto de isla de calor) en su zona cercana (0-500m).\n"
        "- Existe una correlación negativa fuerte y significativa entre pérdida de vegetación (NDVI) y anomalía térmica "
        f"(r = {r_valor:.3f}, p < 0.0001): a menor vegetación cercana, mayor el calentamiento local.\n"
        "- Las plantas de **bajo impacto** están rodeadas en promedio de 79.8% de bosque, mientras que las de **alto impacto** "
        "tienen mayor proporción de terreno agrícola/desbrozado (57%) y huella urbana.\n"
        "- Esto sugiere que la pérdida de cobertura boscosa alrededor de las plantas -más que los paneles en sí- "
        "es un motor clave del efecto térmico observado, con implicaciones sobre tierras agrícolas y bosque remanente adyacente."
    )

# ============ TAB: MAPA Y ANOMALÍA TÉRMICA ============
with tab_mapa:
    st.sidebar.header("Filtros (Mapa y Anomalía Térmica)")

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

    datos_filtrados = datos[
        (datos["year"] == anio_seleccionado)
        & (datos["nivel_impacto"].isin(niveles_seleccionados))
        & (datos["anomalia_termica"].between(*rango_anomalia))
    ]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Plantas mostradas", len(datos_filtrados))
    col2.metric("Anomalía térmica promedio", f"{datos_filtrados['anomalia_termica'].mean():.3f} °C" if len(datos_filtrados) else "N/A")
    col3.metric("Temperatura promedio", f"{datos_filtrados['temperatura_planta'].mean():.1f} °C" if len(datos_filtrados) else "N/A")
    col4.metric("Alto impacto", int((datos_filtrados["nivel_impacto"] == "Alto impacto").sum()))
    col5.metric("Año seleccionado", anio_seleccionado)

    st.divider()

    col_mapa, col_graficos = st.columns([1.2, 1])

    with col_mapa:
        st.subheader(f"Mapa de plantas solares - Imagen satelital de {anio_seleccionado}")
        tile_del_anio = obtener_tile_sentinel2_por_anio(anio_seleccionado)

        mapa = folium.Map(location=[8.5, -80.5], zoom_start=7, tiles=None)
        agregar_capas_base(mapa, tile_del_anio, f"Satelital {anio_seleccionado} (Sentinel-2)")

        for _, fila in datos_filtrados.iterrows():
            folium.CircleMarker(
                location=[fila["latitud"], fila["longitud"]],
                radius=7,
                color=COLORES.get(fila["nivel_impacto"], "gray"),
                fill=True,
                fill_opacity=0.8,
                popup=(
                    f"{fila['nombre']}<br>Nivel: {fila['nivel_impacto']}<br>"
                    f"Temperatura: {fila['temperatura_planta']:.1f} °C<br>"
                    f"Anomalía: {fila['anomalia_termica']:.3f} °C"
                ),
            ).add_to(mapa)

        folium.LayerControl().add_to(mapa)
        st_folium(mapa, width=700, height=500)

    with col_graficos:
        st.subheader("Temperatura y anomalía por nivel de impacto")
        resumen_nivel = datos_filtrados.groupby("nivel_impacto")[["temperatura_planta", "anomalia_termica"]].mean().reset_index()

        fig_temp = px.bar(
            resumen_nivel, x="nivel_impacto", y="temperatura_planta",
            color="nivel_impacto", color_discrete_map=COLORES,
            labels={"temperatura_planta": "Temperatura promedio (°C)", "nivel_impacto": "Nivel"},
            title="Temperatura absoluta",
        )
        st.plotly_chart(fig_temp, use_container_width=True)

        fig_barras = px.bar(
            resumen_nivel, x="nivel_impacto", y="anomalia_termica",
            color="nivel_impacto", color_discrete_map=COLORES,
            labels={"anomalia_termica": "Anomalía térmica (°C)", "nivel_impacto": "Nivel"},
            title="Anomalía térmica",
        )
        st.plotly_chart(fig_barras, use_container_width=True)

        st.subheader("Tendencia anual de anomalía térmica")
        tendencia = datos[datos["id_planta"].isin(datos_filtrados["id_planta"])].groupby("year")["anomalia_termica"].mean().reset_index()
        fig_linea = px.line(tendencia, x="year", y="anomalia_termica", markers=True,
                             labels={"anomalia_termica": "Anomalía térmica (°C)", "year": "Año"})
        st.plotly_chart(fig_linea, use_container_width=True)

    st.divider()
    st.subheader("Tabla de datos filtrados")
    st.dataframe(
        datos_filtrados[["nombre", "nivel_impacto", "temperatura_planta", "anomalia_termica"]]
        .rename(columns={"temperatura_planta": "Temperatura (°C)", "anomalia_termica": "Anomalía (°C)"})
        .sort_values("Anomalía (°C)", ascending=False)
    )

# ============ TAB: NDVI Y COBERTURA DE SUELO ============
with tab_ndvi:
    st.subheader("Correlación entre pérdida de vegetación (NDVI) y anomalía térmica")

    r_valor = np.corrcoef(correlacion["anomalia_ndvi"], correlacion["anomalia_termica"])[0, 1]
    st.metric("Coeficiente de correlación de Pearson", f"{r_valor:.3f}", help="p < 0.0001 (altamente significativo)")

    pendiente, interseccion = np.polyfit(correlacion["anomalia_ndvi"], correlacion["anomalia_termica"], 1)
    x_linea = np.linspace(correlacion["anomalia_ndvi"].min(), correlacion["anomalia_ndvi"].max(), 50)
    y_linea = pendiente * x_linea + interseccion

    fig_scatter = px.scatter(
        correlacion, x="anomalia_ndvi", y="anomalia_termica",
        color="nivel_impacto", color_discrete_map=COLORES,
        hover_name="nombre",
        labels={"anomalia_ndvi": "Anomalía de NDVI (cercano - lejano)", "anomalia_termica": "Anomalía térmica (°C)"},
    )
    fig_scatter.add_trace(go.Scatter(x=x_linea, y=y_linea, mode="lines", name="Tendencia", line=dict(color="black", dash="dash")))
    st.plotly_chart(fig_scatter, use_container_width=True)

    st.caption(
        "Cada punto es una planta solar. A menor anomalía de NDVI (más pérdida de vegetación cerca de la planta), "
        "mayor la anomalía térmica observada."
    )

    st.divider()
    st.subheader("Cobertura de suelo adyacente por nivel de impacto")
    st.caption("Composición del terreno en el anillo cercano (0-500m) de cada planta, según nivel de impacto térmico. Fuente: ESA WorldCover 10m.")

    orden_niveles = ["Bajo impacto", "Impacto moderado", "Alto impacto"]
    columnas_pastel = st.columns(3)

    for columna, nivel in zip(columnas_pastel, orden_niveles):
        fila_nivel = composicion[composicion["nivel_impacto"] == nivel]
        if len(fila_nivel) == 0:
            continue
        fila_nivel = fila_nivel.iloc[0]
        datos_pastel = pd.DataFrame({
            "Cobertura": ["Bosque", "Agrícola", "Urbano", "Agua"],
            "Porcentaje": [fila_nivel["pct_bosque"], fila_nivel["pct_agricola"], fila_nivel["pct_urbano"], fila_nivel["pct_agua"]],
        })
        with columna:
            st.markdown(f"**{nivel}** ({int(fila_nivel['n_plantas'])} plantas)")
            fig_pastel = px.pie(
                datos_pastel, values="Porcentaje", names="Cobertura",
                color="Cobertura", color_discrete_map=COLORES_COBERTURA,
                hole=0.4,
            )
            st.plotly_chart(fig_pastel, use_container_width=True)

# ============ TAB: PLANTA INDIVIDUAL ============
with tab_planta:
    st.subheader("Ficha individual de planta solar")

    nombres_disponibles = sorted(resumen["nombre"].unique())
    planta_seleccionada = st.selectbox("Selecciona una planta", nombres_disponibles)

    fila_planta = resumen[resumen["nombre"] == planta_seleccionada].iloc[0]
    id_planta_sel = fila_planta["id_planta"]
    serie_planta = datos[datos["id_planta"] == id_planta_sel]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Nivel de impacto", fila_planta["nivel_impacto"])
    col2.metric("Temperatura promedio", f"{serie_planta['temperatura_planta'].mean():.1f} °C")
    col3.metric("Anomalía térmica promedio", f"{fila_planta['anomalia_termica_promedio']:.3f} °C")
    col4.metric("NDVI promedio", f"{fila_planta['ndvi_promedio']:.3f}")

    col_mapa_planta, col_serie_planta = st.columns([1, 1])

    with col_mapa_planta:
        st.markdown("**Vista satelital cercana (más reciente)**")
        mapa_planta = folium.Map(
            location=[fila_planta["latitud"], fila_planta["longitud"]],
            zoom_start=16, tiles=None
        )
        agregar_capas_base(mapa_planta, tile_reciente, "Satelital reciente (Sentinel-2)")
        folium.Marker(
            location=[fila_planta["latitud"], fila_planta["longitud"]],
            popup=planta_seleccionada,
        ).add_to(mapa_planta)
        folium.LayerControl().add_to(mapa_planta)
        st_folium(mapa_planta, width=450, height=400)

    with col_serie_planta:
        st.markdown("**Temperatura y anomalía por año**")
        fig_temp_planta = px.line(serie_planta, x="year", y="temperatura_planta", markers=True,
                                   labels={"temperatura_planta": "Temperatura (°C)", "year": "Año"})
        st.plotly_chart(fig_temp_planta, use_container_width=True)

        fig_serie = px.line(serie_planta, x="year", y="anomalia_termica", markers=True,
                             labels={"anomalia_termica": "Anomalía térmica (°C)", "year": "Año"})
        st.plotly_chart(fig_serie, use_container_width=True)

        cobertura_planta = impacto_eco[impacto_eco["id_planta"] == id_planta_sel]
        if len(cobertura_planta) > 0:
            fila_cob = cobertura_planta.iloc[0]
            st.markdown("**Cobertura de suelo cercana (0-500m)**")
            st.write(f"Bosque: {fila_cob['pct_bosque']}% | Agrícola: {fila_cob['pct_agricola']}% | Urbano: {fila_cob['pct_urbano']}% | Agua: {fila_cob['pct_agua']}%")

# ============ TAB: COMPARACIÓN AÑO VS AÑO ============
with tab_comparacion:
    st.subheader("Comparación entre dos años")

    anios_disponibles = sorted(datos["year"].unique())
    col_a, col_b = st.columns(2)
    anio_a = col_a.selectbox("Año A", anios_disponibles, index=0, key="anio_a")
    anio_b = col_b.selectbox("Año B", anios_disponibles, index=len(anios_disponibles) - 1, key="anio_b")

    datos_a = datos[datos["year"] == anio_a][["id_planta", "nombre", "temperatura_planta", "anomalia_termica", "nivel_impacto", "latitud", "longitud"]]
    datos_b = datos[datos["year"] == anio_b][["id_planta", "temperatura_planta", "anomalia_termica"]]

    comparacion = datos_a.merge(datos_b, on="id_planta", suffixes=(f"_{anio_a}", f"_{anio_b}"))
    comparacion["cambio"] = comparacion[f"anomalia_termica_{anio_b}"] - comparacion[f"anomalia_termica_{anio_a}"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric(f"Temperatura {anio_a}", f"{comparacion[f'temperatura_planta_{anio_a}'].mean():.1f} °C")
    col2.metric(f"Temperatura {anio_b}", f"{comparacion[f'temperatura_planta_{anio_b}'].mean():.1f} °C")
    col3.metric(f"Anomalía {anio_a} -> {anio_b}", f"{comparacion[f'anomalia_termica_{anio_a}'].mean():.3f} -> {comparacion[f'anomalia_termica_{anio_b}'].mean():.3f} °C")
    col4.metric("Cambio promedio de anomalía", f"{comparacion['cambio'].mean():+.3f} °C")

    st.divider()
    col_mapa_a, col_mapa_b = st.columns(2)

    tile_a = obtener_tile_sentinel2_por_anio(anio_a)
    tile_b = obtener_tile_sentinel2_por_anio(anio_b)

    with col_mapa_a:
        st.markdown(f"**Mapa {anio_a}**")
        mapa_a = folium.Map(location=[8.5, -80.5], zoom_start=6.3, tiles=None)
        agregar_capas_base(mapa_a, tile_a, f"Satelital {anio_a}")
        for _, fila in comparacion.iterrows():
            folium.CircleMarker(
                location=[fila["latitud"], fila["longitud"]],
                radius=6,
                color=COLORES.get(fila["nivel_impacto"], "gray"),
                fill=True, fill_opacity=0.8,
                popup=f"{fila['nombre']}: {fila[f'temperatura_planta_{anio_a}']:.1f} °C (anomalía {fila[f'anomalia_termica_{anio_a}']:.3f} °C)",
            ).add_to(mapa_a)
        folium.LayerControl().add_to(mapa_a)
        st_folium(mapa_a, width=380, height=400, key="mapa_comp_a")

    with col_mapa_b:
        st.markdown(f"**Mapa {anio_b}**")
        mapa_b = folium.Map(location=[8.5, -80.5], zoom_start=6.3, tiles=None)
        agregar_capas_base(mapa_b, tile_b, f"Satelital {anio_b}")
        for _, fila in comparacion.iterrows():
            folium.CircleMarker(
                location=[fila["latitud"], fila["longitud"]],
                radius=6,
                color=COLORES.get(fila["nivel_impacto"], "gray"),
                fill=True, fill_opacity=0.8,
                popup=f"{fila['nombre']}: {fila[f'temperatura_planta_{anio_b}']:.1f} °C (anomalía {fila[f'anomalia_termica_{anio_b}']:.3f} °C)",
            ).add_to(mapa_b)
        folium.LayerControl().add_to(mapa_b)
        st_folium(mapa_b, width=380, height=400, key="mapa_comp_b")

    st.divider()
    st.subheader("Plantas con mayor incremento de anomalía térmica")
    top_incremento = comparacion.sort_values("cambio", ascending=False).head(10)
    fig_cambio = px.bar(
        top_incremento, x="nombre", y="cambio",
        labels={"cambio": f"Cambio en anomalía térmica {anio_a} - {anio_b} (°C)", "nombre": "Planta"},
    )
    st.plotly_chart(fig_cambio, use_container_width=True)

# ============ TAB: ACERCA DEL PROYECTO ============
with tab_acerca:
    st.subheader("Acerca del proyecto")
    st.markdown(
        "**Objetivo:** evaluar si existe un efecto de isla de calor (anomalía térmica) en zonas adyacentes a "
        "plantas fotovoltaicas en Panamá, y su relación con la pérdida de cobertura vegetal.\n\n"
        "**Fuentes de datos (Google Earth Engine):**\n"
        "- Temperatura superficial (LST): MODIS MOD11A2, banda LST_Day_1km, resolución 1km, compuesto de 8 días.\n"
        "- Vegetación (NDVI): MODIS MOD13Q1, resolución 250m, compuesto de 16 días.\n"
        "- Cobertura de suelo: ESA WorldCover, resolución 10m.\n"
        "- Imagen satelital visual: Sentinel-2 (mediana anual o de los últimos 90 días, filtrado por nubosidad menor a 20%).\n\n"
        "**Metodología:**\n"
        "1. Se recolectaron 52 coordenadas de plantas solares en Panamá (49 tras limpieza de duplicados).\n"
        "2. Se generaron 3 anillos concéntricos por planta (0-500m, 500m-1km, 1-2km) con GeoPandas.\n"
        "3. Se extrajo LST y NDVI promedio por anillo y por año (2019-2025) desde Google Earth Engine.\n"
        "4. Se calculó un índice de anomalía térmica: LST(0-500m) menos LST(1-2km).\n"
        "5. Se aplicó clustering K-means para clasificar las plantas en 3 niveles de impacto térmico.\n"
        "6. Se correlacionó la anomalía de NDVI con la anomalía térmica, y se analizó la composición de "
        "cobertura de suelo adyacente para vincular el hallazgo con pérdida de vegetación e impacto en "
        "ecosistemas/tierras agrícolas adyacentes.\n\n"
        "**Limitaciones:**\n"
        "- No se cuenta con fecha de instalación exacta de cada planta, por lo que la comparación usa el anillo "
        "lejano (1-2km) como zona de referencia espacial en lugar de una línea base temporal pre-instalación.\n"
        "- La resolución de MODIS (1km) limita la precisión espacial del análisis térmico respecto al tamaño "
        "real de las plantas."
    )