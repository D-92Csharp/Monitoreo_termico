import ee
import json
import sqlite3
import pandas as pd

# --- Inicializar GEE ---
ee.Initialize(project='monitoreo-termico-solar')

# --- Cargar los anillos (buffers) como FeatureCollection de GEE ---
with open('data/processed/buffers_plantas.geojson', encoding='utf-8') as f:
    geojson_data = json.load(f)

fc = ee.FeatureCollection(geojson_data)
print(f"Anillos cargados en GEE: {fc.size().getInfo()}")

# --- Años a procesar ---
anios = list(range(2019, 2026))  # 2019 a 2025

resultados = []

for anio in anios:
    print(f"Procesando año {anio}...")
    fecha_inicio = f"{anio}-01-01"
    fecha_fin = f"{anio}-12-31"

    # --- LST (Temperatura Superficial) ---
    lst_coleccion = (
        ee.ImageCollection("MODIS/061/MOD11A2")
        .filterDate(fecha_inicio, fecha_fin)
        .select("LST_Day_1km")
    )
    lst_promedio = lst_coleccion.mean().multiply(0.02).subtract(273.15)  # Kelvin*0.02 -> Celsius

    # --- NDVI (Vegetación) ---
    ndvi_coleccion = (
        ee.ImageCollection("MODIS/061/MOD13Q1")
        .filterDate(fecha_inicio, fecha_fin)
        .select("NDVI")
    )
    ndvi_promedio = ndvi_coleccion.mean().multiply(0.0001)

    # --- Combinar ambas bandas en una sola imagen ---
    imagen_combinada = lst_promedio.rename("lst_celsius").addBands(
        ndvi_promedio.rename("ndvi")
    )

    # --- Calcular promedio dentro de cada anillo (reduceRegions procesa todos a la vez) ---
    stats = imagen_combinada.reduceRegions(
        collection=fc,
        reducer=ee.Reducer.mean(),
        scale=250,
    )

    datos_anio = stats.getInfo()

    for feature in datos_anio["features"]:
        props = feature["properties"]
        resultados.append({
            "id_planta": props.get("id_planta"),
            "nombre": props.get("nombre"),
            "anillo": props.get("anillo"),
            "radio_interno_m": props.get("radio_interno_m"),
            "radio_externo_m": props.get("radio_externo_m"),
            "year": anio,
            "lst_celsius": props.get("lst_celsius"),
            "ndvi": props.get("ndvi"),
        })

# --- Convertir a DataFrame ---
df_resultados = pd.DataFrame(resultados)
print(f"\nTotal de registros extraídos: {len(df_resultados)}")
print(df_resultados.head(10))

# --- Guardar en SQLite ---
conn = sqlite3.connect("data/processed/monitoreo_termico.db")
df_resultados.to_sql("mediciones_termicas", conn, if_exists="replace", index=False)
conn.close()

print("\nGuardado en data/processed/monitoreo_termico.db (tabla: mediciones_termicas)")

# --- También guardar como CSV de respaldo ---
df_resultados.to_csv("data/processed/mediciones_termicas.csv", index=False)
print("Respaldo CSV: data/processed/mediciones_termicas.csv")
