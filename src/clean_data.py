import pandas as pd
import re

# --- Cargar datos crudos ---
df = pd.read_csv("data/raw/plantas_solares_panama_google_maps.csv", encoding="utf-8-sig")
df.columns = [c.strip().lower() for c in df.columns]
print(f"Filas originales: {len(df)}")

# --- Detectar nombres en formato de coordenadas GPS (ej: 8°08'46.3"N 81°02'40.6"W) ---
patron_gps = re.compile(r"\d+°\d+'\d+(\.\d+)?\"")

def es_nombre_gps(nombre):
    return bool(patron_gps.search(str(nombre)))

df["nombre_es_gps"] = df["nombre"].apply(es_nombre_gps)

# --- Eliminar duplicados por coordenadas exactas ---
# Al agrupar por lat/lon idénticos, se prefiere el nombre que NO sea formato GPS
def elegir_mejor_nombre(grupo):
    no_gps = grupo[~grupo["nombre_es_gps"]]
    if len(no_gps) > 0:
        return no_gps.iloc[0]
    return grupo.iloc[0]

filas_limpias = []
duplicados_log = []

for (lat, lon), grupo in df.groupby(["latitud", "longitud"]):
    if len(grupo) > 1:
        duplicados_log.append(f"  Coordenada ({lat}, {lon}): {list(grupo['nombre'])} -> se conservó: ", )
        mejor = elegir_mejor_nombre(grupo)
        duplicados_log[-1] += f"'{mejor['nombre']}'"
        filas_limpias.append(mejor)
    else:
        filas_limpias.append(grupo.iloc[0])

df_limpio = pd.DataFrame(filas_limpias).reset_index(drop=True)

# --- Etiquetar nombres GPS restantes (los que no tenían duplicado) como 'sin nombre' ---
contador_sin_nombre = 1
for idx, row in df_limpio.iterrows():
    if row["nombre_es_gps"]:
        df_limpio.at[idx, "nombre"] = f"Planta solar sin nombre {contador_sin_nombre}"
        contador_sin_nombre += 1

df_limpio = df_limpio.drop(columns=["nombre_es_gps"])

# --- Agregar ID único ---
df_limpio.insert(0, "id_planta", range(1, len(df_limpio) + 1))

# --- Guardar resultado ---
df_limpio.to_csv("data/processed/plantas_solares_limpio.csv", index=False, encoding="utf-8")

# --- Resumen ---
print(f"\nDuplicados encontrados y resueltos ({len(duplicados_log)}):")
for linea in duplicados_log:
    print(linea)
print(f"\nFilas finales: {len(df_limpio)}")
print(f"Guardado en: data/processed/plantas_solares_limpio.csv")
