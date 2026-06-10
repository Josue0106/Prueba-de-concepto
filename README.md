# Prueba de concepto: sombra en bancas del parque central de Grecia

Este repositorio contiene una prueba de concepto para validar si el flujo propuesto en el laboratorio es técnicamente viable antes de construir un producto final.

## Qué demuestra

- Genera datos sintéticos de bancas, árboles, senderos y luminarias dentro de un área aproximada del parque central de Grecia.
- Intenta descargar una referencia local desde OSM mediante Overpass para comparar bancas, árboles, senderos y luminarias existentes.
- Calcula cobertura de sombra para cada banca en tres franjas horarias: mañana, mediodía y tarde.
- Exporta un mapa interactivo en Leaflet/Folium con selector de franja, capas activables y pop-ups informativos.
- Produce archivos JSON con resumen del análisis y reporte de ejecución.

## Preparación del entorno

El entorno virtual no se versiona. Cada persona debe crearlo localmente desde cero.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install geopandas shapely folium requests pandas
```

En Windows PowerShell, la activación equivalente es:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Ejecución

```bash
python src/poc_parque_grecia.py
```

También puedes ajustar la simulación:

```bash
python src/poc_parque_grecia.py --benches 14 --trees 10 --lamps 8 --morning-radius 9.0 --noon-radius 4.5 --afternoon-radius 8.5
```

## Salidas

- `data/generated/synthetic_features.geojson`
- `data/generated/park_polygon.geojson`
- `data/generated/osm_reference.geojson` si Overpass responde correctamente
- `output/analysis_summary.json`
- `output/run_report.json`
- `output/parque_grecia_sombra.html`

## Heurística de sombra

- `sin sombra`: ninguna fuente de sombra cubre la banca.
- `sombra parcial`: una sola copa cubre la banca.
- `bien cubierta`: dos o más copas cubren la banca.

## Alcance de la PoC

El modelo de sombra es simplificado y usa radios fijos ajustables por franja horaria. Los senderos y luminarias se incluyen como capas de contexto para demostrar el visor, pero no participan en el cálculo de sombra.

Esta versión valida el flujo técnico con datos sintéticos y referencia OSM opcional; no sustituye el levantamiento de campo, la validación comunitaria ni un modelo solar físico del producto final.
