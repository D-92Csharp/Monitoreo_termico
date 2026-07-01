import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

# --- Cargar datos limpios ---
df = pd.read_csv("data/processed/plantas_solares_limpio.csv", encoding="utf-8")
print(f"Plantas cargadas: {len(df)}")

# --- Convertir a GeoDataFrame (puntos) en WGS84 ---
geometry = [Point(lon, lat) for lon, lat in zip(df["longitud"], df["latitud"])]
gdf = gpd.GeoDataFrame(df, geometry=geometry, crs="EPSG:4326")

# --- Reproyectar a UTM 17N (metros) para calcular buffers con precisión ---
gdf_utm = gdf.to_crs("EPSG:32617")

# --- Definir anillos concéntricos ---
anillos = [
    ("0_500m", 0, 500),
    ("500_1000m", 500, 1000),
    ("1000_2000m", 1000, 2000),
]

# --- Construir geometrías de cada anillo por planta ---
registros_anillos = []

for _, planta in gdf_utm.iterrows():
    punto = planta.geometry
    for nombre_anillo, radio_interno, radio_externo in anillos:
        circulo_externo = punto.buffer(radio_externo)
        if radio_interno > 0:
            circulo_interno = punto.buffer(radio_interno)
            anillo_geom = circulo_externo.difference(circulo_interno)
        else:
            anillo_geom = circulo_externo

        registros_anillos.append({
            "id_planta": planta["id_planta"],
            "nombre": planta["nombre"],
            "anillo": nombre_anillo,
            "radio_interno_m": radio_interno,
            "radio_externo_m": radio_externo,
            "geometry": anillo_geom,
        })

gdf_anillos = gpd.GeoDataFrame(registros_anillos, crs="EPSG:32617")

# --- Reproyectar de vuelta a WGS84 (lat/lon) para usar con Google Earth Engine ---
gdf_anillos_wgs84 = gdf_anillos.to_crs("EPSG:4326")

# --- Guardar como GeoJSON (formato estándar para geoespacial, lo usaremos en GEE) ---
output_path = "data/processed/buffers_plantas.geojson"
gdf_anillos_wgs84.to_file(output_path, driver="GeoJSON")

print(f"\nTotal de anillos generados: {len(gdf_anillos_wgs84)}  (49 plantas x 3 anillos)")
print(f"Guardado en: {output_path}")
print("\nEjemplo de las primeras filas:")
print(gdf_anillos_wgs84[["id_planta", "nombre", "anillo"]].head(6))
