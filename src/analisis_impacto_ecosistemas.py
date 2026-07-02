import pandas as pd

cobertura = pd.read_csv("data/processed/cobertura_suelo.csv")
resumen = pd.read_csv("data/processed/resumen_clustering.csv")

# --- Nos enfocamos en el anillo cercano (0-500m), donde se concentra el impacto térmico ---
cobertura_cercana = cobertura[cobertura["anillo"] == "0_500m"].copy()

# --- Unir con nivel de impacto ---
datos = cobertura_cercana.merge(
    resumen[["id_planta", "nivel_impacto", "anomalia_termica_promedio"]], on="id_planta"
)

print("="*70)
print("COMPOSICIÓN DE COBERTURA DE SUELO (anillo 0-500m) POR NIVEL DE IMPACTO")
print("="*70)

composicion = (
    datos.groupby("nivel_impacto")
    .agg(
        n_plantas=("id_planta", "count"),
        pct_bosque=("pct_bosque", "mean"),
        pct_agricola=("pct_agricola", "mean"),
        pct_urbano=("pct_urbano", "mean"),
        pct_agua=("pct_agua", "mean"),
        anomalia_termica_promedio=("anomalia_termica_promedio", "mean"),
    )
    .round(1)
    .reset_index()
)

print(composicion.to_string(index=False))

# --- Guardar para el dashboard ---
composicion.to_csv("data/processed/composicion_suelo_por_impacto.csv", index=False)
datos.to_csv("data/processed/impacto_ecosistemas_adyacentes.csv", index=False)

print("\nGuardado en:")
print(" - data/processed/composicion_suelo_por_impacto.csv (para el dashboard)")
print(" - data/processed/impacto_ecosistemas_adyacentes.csv (detalle completo)")
