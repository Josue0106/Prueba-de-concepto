from __future__ import annotations

import argparse
from pathlib import Path

from poc_steps import DEFAULT_COUNTS, SATELLITE_TILE_URL, SHADOW_RADII_METERS, RunConfig, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prueba de concepto de sombra en bancas del parque central de Grecia."
    )
    parser.add_argument(
        "--input-geojson",
        type=Path,
        help="GeoJSON externo con elementos levantados en campo. Si se omite, se generan datos sintéticos.",
    )
    parser.add_argument(
        "--skip-osm",
        action="store_true",
        help="No consultar ni cargar referencia OSM.",
    )
    parser.add_argument(
        "--refresh-osm",
        action="store_true",
        help="Forzar una nueva consulta Overpass aunque exista una referencia cacheada.",
    )
    parser.add_argument(
        "--satellite-tile-url",
        default=SATELLITE_TILE_URL,
        help="URL XYZ para la capa satelital. Debe contener {z}, {x} y {y}.",
    )
    parser.add_argument(
        "--no-satellite",
        action="store_true",
        help="No agregar la capa base satelital alternativa.",
    )
    parser.add_argument(
        "--benches",
        type=int,
        default=DEFAULT_COUNTS["benches"],
        help="Cantidad de bancas sintéticas a generar.",
    )
    parser.add_argument(
        "--trees",
        type=int,
        default=DEFAULT_COUNTS["trees"],
        help="Cantidad de árboles sintéticos a generar.",
    )
    parser.add_argument(
        "--lamps",
        type=int,
        default=DEFAULT_COUNTS["lamps"],
        help="Cantidad de luminarias sintéticas a generar.",
    )
    parser.add_argument(
        "--morning-radius",
        type=float,
        default=SHADOW_RADII_METERS["morning"],
        help="Radio de sombra para la mañana, en metros.",
    )
    parser.add_argument(
        "--noon-radius",
        type=float,
        default=SHADOW_RADII_METERS["noon"],
        help="Radio de sombra para el mediodía, en metros.",
    )
    parser.add_argument(
        "--afternoon-radius",
        type=float,
        default=SHADOW_RADII_METERS["afternoon"],
        help="Radio de sombra para la tarde, en metros.",
    )
    return parser


def config_from_args(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        benches=args.benches,
        trees=args.trees,
        lamps=args.lamps,
        input_geojson=args.input_geojson,
        fetch_osm=not args.skip_osm,
        refresh_osm=args.refresh_osm,
        satellite_tile_url=None if args.no_satellite else args.satellite_tile_url,
        shadow_radii={
            "morning": args.morning_radius,
            "noon": args.noon_radius,
            "afternoon": args.afternoon_radius,
        },
    )


def main() -> None:
    parser = build_parser()
    outputs = run_pipeline(config_from_args(parser.parse_args()))
    print(f"Mapa generado: {outputs.output_html}")
    print(f"Resumen generado: {outputs.analysis_summary}")
    print(f"Recomendaciones generadas: {outputs.bench_recommendations}")


if __name__ == "__main__":
    main()
