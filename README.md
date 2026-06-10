# Prueba de concepto: sombra en bancas del parque central de Grecia

Este repositorio contiene una primera versión funcional de la prueba de concepto.

## Qué hace

- Genera datos sintéticos de bancas y árboles dentro de un área aproximada del parque central de Grecia.
- Intenta descargar una referencia local de OSM mediante Overpass para bancas y árboles.
- Calcula cobertura de sombra por tres franjas horarias: mañana, mediodía y tarde.
- Exporta un mapa interactivo en Leaflet usando Folium con un selector único de franja horaria.

## Ejecución

1. Crear un entorno virtual e instalar dependencias.
2. Ejecutar el script principal.

```bash
python src/poc_parque_grecia.py
```

También puedes ajustar la simulación:

```bash
python src/poc_parque_grecia.py --benches 14 --trees 10 --morning-radius 9.0 --noon-radius 4.5 --afternoon-radius 8.5
```

## Salidas

- `data/generated/synthetic_features.geojson`
- `data/generated/osm_reference.geojson` si Overpass responde correctamente
- `output/analysis_summary.json`
- `output/parque_grecia_sombra.html`

## Heurística de sombra

- `sin sombra`: ninguna fuente de sombra cubre la banca.
- `sombra parcial`: una sola copa cubre la banca.
- `bien cubierta`: dos o más copas cubren la banca.

## Nota

El modelo de sombra es simplificado y usa radios fijos ajustables por franja horaria. Esta versión está pensada para validar la viabilidad del flujo, no para sustituir mediciones de campo.

El ejemplo está anclado visualmente como Parque de Grecia y usa coordenadas aproximadas para la demostración; si luego compartes coordenadas exactas, se ajusta el centro del mapa.
