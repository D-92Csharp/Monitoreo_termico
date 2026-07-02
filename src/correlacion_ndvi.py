import sqlite3
import pandas as pd
from scipy import stats

# --- Cargar mediciones (usamos el CSV, ya que es lo que tenemos siempre disponible) ---
mediciones = pd.read_csv("data/processed/mediciones_termicas.csv")

# --- Pivotear LST y NDVI por anillo ---
pivot_lst = mediciones.pivot_table(
    index=["id_planta", "nombre", "year"], columns="anillo", values="lst_celsius"
).reset_index()
pivot_ndvi = mediciones.pivot_table(
    index=["id_planta", "nombre", "year"], columns="anillo", values="ndvi"
).reset_index()

# --- Anomalías: cercano (0-500m) menos lejano (1000-2000m) ---
pivot_lst["anomalia_termica"] = pivot_lst["0_500m"] - pivot_lst["1000_2000m"]
pivot_ndvi["anomalia_ndvi"] = pivot_ndvi["0_500m"] - pivot_ndvi["1000_2000m"]

# --- Promediar a través de los años: un valor representativo por planta ---
anomalia_termica_planta = pivot_lst.groupby(["id_planta", "nombre"])["anomalia_termica"].mean().reset_index()
anomalia_ndvi_planta = pivot_ndvi.groupby(["id_planta", "nombre"])["anomalia_ndvi"].mean().reset_index()

combinado = anomalia_termica_planta.merge(anomalia_ndvi_planta, on=["id_planta", "nombre"])

# --- Unir con nivel de impacto ya calculado ---
resumen = pd.read_csv("data/processed/resumen_clustering.csv")
combinado = combinado.merge(resumen[["id_planta", "nivel_impacto"]], on="id_planta")

# --- Correlación entre pérdida de NDVI y anomalía térmica ---
correlacion, p_valor = stats.pearsonr(combinado["anomalia_ndvi"], combinado["anomalia_termica"])

print(f"Correlación de Pearson (NDVI vs Temperatura): {correlacion:.3f}")
print(f"Valor p: {p_valor:.4f}")
print(f"{'Significativo (p<0.05)' if p_valor < 0.05 else 'No significativo'}")

print("\nAnomalía NDVI promedio por nivel de impacto:")
print(combinado.groupby("nivel_impacto")["anomalia_ndvi"].mean().round(4))

# --- Guardar para usar en el dashboard / artículo ---
combinado.to_csv("data/processed/correlacion_ndvi_temperatura.csv", index=False)
print("\nGuardado en data/processed/correlacion_ndvi_temperatura.csv")
