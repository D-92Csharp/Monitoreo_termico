import sqlite3
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# --- Cargar datos de mediciones ---
conn = sqlite3.connect("data/processed/monitoreo_termico.db")
df = pd.read_sql("SELECT * FROM mediciones_termicas", conn)
conn.close()

print(f"Registros cargados: {len(df)}")

# --- Pivotear: una columna de LST por cada anillo, por planta y año ---
pivot = df.pivot_table(
    index=["id_planta", "nombre", "year"],
    columns="anillo",
    values="lst_celsius",
).reset_index()

# --- Calcular anomalía térmica anual: cerca (0-500m) menos lejos (1000-2000m) ---
pivot["anomalia_termica"] = pivot["0_500m"] - pivot["1000_2000m"]

# --- Promedio de NDVI por planta y año (para tener contexto de vegetación) ---
ndvi_promedio = df.groupby(["id_planta", "year"])["ndvi"].mean().reset_index()
ndvi_promedio = ndvi_promedio.rename(columns={"ndvi": "ndvi_promedio"})

pivot = pivot.merge(ndvi_promedio, on=["id_planta", "year"], how="left")

# --- Promediar a través de los años: un valor representativo por planta ---
resumen_planta = pivot.groupby(["id_planta", "nombre"]).agg(
    anomalia_termica_promedio=("anomalia_termica", "mean"),
    ndvi_promedio=("ndvi_promedio", "mean"),
).reset_index()

print("\nResumen por planta (primeras filas):")
print(resumen_planta.head())

# --- K-means: 3 clusters (bajo / moderado / alto impacto) ---
X = resumen_planta[["anomalia_termica_promedio", "ndvi_promedio"]].copy()
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
resumen_planta["cluster_raw"] = kmeans.fit_predict(X_scaled)

# --- Reordenar clusters de menor a mayor anomalía térmica promedio ---
orden_clusters = (
    resumen_planta.groupby("cluster_raw")["anomalia_termica_promedio"]
    .mean()
    .sort_values()
    .index.tolist()
)
etiquetas = {orden_clusters[0]: "Bajo impacto", orden_clusters[1]: "Impacto moderado", orden_clusters[2]: "Alto impacto"}
resumen_planta["nivel_impacto"] = resumen_planta["cluster_raw"].map(etiquetas)
resumen_planta = resumen_planta.drop(columns=["cluster_raw"])

print("\nDistribución de plantas por nivel de impacto:")
print(resumen_planta["nivel_impacto"].value_counts())

print("\nAnomalía térmica promedio por nivel:")
print(resumen_planta.groupby("nivel_impacto")["anomalia_termica_promedio"].mean().round(3))

# --- Agregar coordenadas para poder mapear en el dashboard ---
coords = pd.read_csv("data/processed/plantas_solares_limpio.csv", encoding="utf-8")
resumen_planta = resumen_planta.merge(
    coords[["id_planta", "latitud", "longitud"]], on="id_planta", how="left"
)

# --- Guardar resultado final ---
conn = sqlite3.connect("data/processed/monitoreo_termico.db")
resumen_planta.to_sql("resumen_clustering", conn, if_exists="replace", index=False)
conn.close()

resumen_planta.to_csv("data/processed/resumen_clustering.csv", index=False)

print("\nGuardado en SQLite (tabla: resumen_clustering) y en data/processed/resumen_clustering.csv")
