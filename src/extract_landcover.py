import ee
import json
import pandas as pd

# --- Inicializar GEE ---
ee.Initialize(project='monitoreo-termico-solar')

# --- Cargar los anillos ---
with open('data/processed/buffers_plantas.geojson', encoding='utf-8') as f:
    geojson_data = json.load(f)

fc = ee.FeatureCollection(geojson_data)
print(f"Anillos cargados: {fc.size().getInfo()}")

# --- Cargar ESA WorldCover (cobertura de suelo, 10m, año base 2021) ---
worldcover = ee.ImageCollection("ESA/WorldCover/v200").first()

# --- Clases relevantes según la leyenda oficial de WorldCover ---
# 10 = Bosque | 30 = Pastizal | 40 = Cultivos agrícolas | 50 = Urbano | 80 = Agua permanente | 95 = Manglar
es_bosque = worldcover.eq(10).Or(worldcover.eq(95))       # bosque + manglar
es_agricola = worldcover.eq(40).Or(worldcover.eq(30))     # cultivos + pastizal
es_urbano = worldcover.eq(50)
es_agua = worldcover.eq(80)

# --- Combinar en una sola imagen multibanda (cada banda = fracción 0/1 por píxel) ---
imagen_clases = (
    es_bosque.rename("frac_bosque")
    .addBands(es_agricola.rename("frac_agricola"))
    .addBands(es_urbano.rename("frac_urbano"))
    .addBands(es_agua.rename("frac_agua"))
)

# --- Calcular el % de cada clase dentro de cada anillo (mean de 0/1 = fracción de píxeles) ---
stats = imagen_clases.reduceRegions(
    collection=fc,
    reducer=ee.Reducer.mean(),
    scale=10,
)

resultado = stats.getInfo()

registros = []
for feature in resultado["features"]:
    props = feature["properties"]
    registros.append({
        "id_planta": props.get("id_planta"),
        "nombre": props.get("nombre"),
        "anillo": props.get("anillo"),
        "pct_bosque": round((props.get("frac_bosque") or 0) * 100, 1),
        "pct_agricola": round((props.get("frac_agricola") or 0) * 100, 1),
        "pct_urbano": round((props.get("frac_urbano") or 0) * 100, 1),
        "pct_agua": round((props.get("frac_agua") or 0) * 100, 1),
    })

df_landcover = pd.DataFrame(registros)
df_landcover.to_csv("data/processed/cobertura_suelo.csv", index=False)

print(f"\nTotal de registros: {len(df_landcover)}")
print(df_landcover.head(10))
print("\nGuardado en data/processed/cobertura_suelo.csv")

