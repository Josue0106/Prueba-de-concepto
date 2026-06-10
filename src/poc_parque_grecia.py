from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import folium
import geopandas as gpd
import requests
from shapely.geometry import LineString, Point, Polygon


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "generated"
OUTPUT_DIR = ROOT / "output"

PARK_NAME = "Parque de Grecia"
# Centro actualizado al Parque Central de Grecia (usuario): 10.07282 N, -84.31171 W
PARK_CENTER = (10.07282, -84.31171)
PARK_BOUNDS = {
    "min_lat": 10.0708,
    "min_lon": -84.3152,
    "max_lat": 10.0730,
    "max_lon": -84.3128,
}
PROJECTED_CRS = "EPSG:32616"

SHADOW_RADII_METERS = {
    "morning": 8.5,
    "noon": 5.0,
    "afternoon": 8.0,
}

TIME_LABELS = {
    "morning": "mañana",
    "noon": "mediodía",
    "afternoon": "tarde",
}

STATUS_COLORS = {
    "sin sombra": "#d1495b",
    "sombra parcial": "#f4a261",
    "bien cubierta": "#2a9d8f",
}

DEFAULT_COUNTS = {
    "benches": 12,
    "trees": 8,
    "lamps": 6,
}


@dataclass(frozen=True)
class FeatureSet:
    benches: gpd.GeoDataFrame
    trees: gpd.GeoDataFrame
    paths: gpd.GeoDataFrame
    lamps: gpd.GeoDataFrame


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(value, maximum))


def synthetic_points(count: int, geometry_type: str, seed: int, polygon: Optional[Polygon] = None) -> list[dict]:
    random.seed(seed)
    features = []
    if geometry_type == "bench":
        anchors = [(10.0712, -84.3149), (10.0719, -84.3141), (10.0725, -84.3134)]
        spread_lat = 0.00016
        spread_lon = 0.00018
    elif geometry_type == "tree":
        anchors = [(10.0709, -84.3149), (10.0720, -84.3142), (10.0728, -84.3131)]
        spread_lat = 0.00020
        spread_lon = 0.00020
    elif geometry_type == "lamp":
        anchors = [(10.0711, -84.3147), (10.0719, -84.3139), (10.0726, -84.3132)]
        spread_lat = 0.00012
        spread_lon = 0.00012
    else:
        raise ValueError(f"Unsupported synthetic geometry type: {geometry_type}")

    for index in range(count):
        anchor_lat, anchor_lon = anchors[index % len(anchors)]
        if polygon is None:
            lat = clamp(random.gauss(anchor_lat, spread_lat), PARK_BOUNDS["min_lat"], PARK_BOUNDS["max_lat"])
            lon = clamp(random.gauss(anchor_lon, spread_lon), PARK_BOUNDS["min_lon"], PARK_BOUNDS["max_lon"])
        else:
            # rejection sampling inside polygon's bounds
            minx, miny, maxx, maxy = polygon.bounds
            attempt = 0
            while True:
                attempt += 1
                # sample lon/lat within polygon bbox
                lon = random.uniform(minx, maxx)
                lat = random.uniform(miny, maxy)
                if polygon.contains(Point(lon, lat)):
                    break
                if attempt > 200:
                    # fallback to Gaussian near anchor if polygon sampling fails
                    lat = clamp(random.gauss(anchor_lat, spread_lat), PARK_BOUNDS["min_lat"], PARK_BOUNDS["max_lat"])
                    lon = clamp(random.gauss(anchor_lon, spread_lon), PARK_BOUNDS["min_lon"], PARK_BOUNDS["max_lon"])
                    break
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "id": f"{geometry_type[:1].upper()}{index + 1:02d}",
                    "kind": geometry_type,
                    "source": "synthetic",
                },
            }
        )
    return features


def synthetic_paths(polygon: Polygon) -> list[dict]:
    minx, miny, maxx, maxy = polygon.bounds
    width = maxx - minx
    height = maxy - miny
    midx = minx + width / 2
    midy = miny + height / 2

    path_coords = [
        [(minx + width * 0.12, midy), (maxx - width * 0.12, midy)],
        [(midx, miny + height * 0.12), (midx, maxy - height * 0.12)],
        [(minx + width * 0.18, miny + height * 0.18), (maxx - width * 0.18, maxy - height * 0.18)],
    ]

    return [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "id": f"S{index + 1:02d}",
                "kind": "path",
                "source": "synthetic",
            },
        }
        for index, coords in enumerate(path_coords)
    ]


def fetch_park_polygon() -> Optional[Polygon]:
    endpoint = "https://overpass-api.de/api/interpreter"
    # first try: find by name inside bounding box
    query_name = f"""
    [out:json][timeout:25];
    (
      relation["leisure"="park"]["name"~"Grecia",i]({PARK_BOUNDS['min_lat']},{PARK_BOUNDS['min_lon']},{PARK_BOUNDS['max_lat']},{PARK_BOUNDS['max_lon']});
      way["leisure"="park"]["name"~"Grecia",i]({PARK_BOUNDS['min_lat']},{PARK_BOUNDS['min_lon']},{PARK_BOUNDS['max_lat']},{PARK_BOUNDS['max_lon']});
    );
    out body geom;
    """
    try:
        response = requests.get(endpoint, params={"data": query_name}, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception:
        data = {"elements": []}

    for element in data.get("elements", []):
        coords = element.get("geometry")
        if not coords:
            continue
        try:
            poly_coords = [(pt["lon"], pt["lat"]) for pt in coords]
            polygon = Polygon(poly_coords)
            if polygon.is_valid and polygon.area > 0:
                return polygon
        except Exception:
            continue

    # second try: search for park ways/relations around the given center (300m)
    lat_c, lon_c = PARK_CENTER[0], PARK_CENTER[1]
    query_around = f"""
    [out:json][timeout:25];
    (
      relation(around:300,{lat_c},{lon_c})["leisure"="park"];
      way(around:300,{lat_c},{lon_c})["leisure"="park"];
    );
    out body geom;
    """
    try:
        response = requests.get(endpoint, params={"data": query_around}, timeout=30)
        response.raise_for_status()
        data2 = response.json()
    except Exception:
        data2 = {"elements": []}

    for element in data2.get("elements", []):
        coords = element.get("geometry")
        if not coords:
            continue
        try:
            poly_coords = [(pt["lon"], pt["lat"]) for pt in coords]
            polygon = Polygon(poly_coords)
            if polygon.is_valid and polygon.area > 0:
                return polygon
        except Exception:
            continue

    return None


def generate_synthetic_geojson(bench_count: int, tree_count: int, lamp_count: int) -> Path:
    park_poly = fetch_park_polygon()
    if park_poly is None:
        # fallback: create a circular park polygon (projected buffer) around PARK_CENTER
        try:
            from shapely.ops import transform
            import pyproj

            lon_c, lat_c = PARK_CENTER[1], PARK_CENTER[0]
            # transformer: lon,lat -> projected (meters)
            proj = pyproj.Transformer.from_crs("EPSG:4326", PROJECTED_CRS, always_xy=True).transform
            inv = pyproj.Transformer.from_crs(PROJECTED_CRS, "EPSG:4326", always_xy=True).transform
            center_proj = transform(proj, Point(lon_c, lat_c))
            buffer_m = 40
            poly_proj = center_proj.buffer(buffer_m)
            park_poly = transform(inv, poly_proj)
        except Exception:
            # final fallback: use bounding box as polygon (lon,lat ordering)
            min_lat = PARK_BOUNDS["min_lat"]
            min_lon = PARK_BOUNDS["min_lon"]
            max_lat = PARK_BOUNDS["max_lat"]
            max_lon = PARK_BOUNDS["max_lon"]
            park_poly = Polygon([(min_lon, min_lat), (min_lon, max_lat), (max_lon, max_lat), (max_lon, min_lat), (min_lon, min_lat)])

    # write park polygon for debugging/visualization
    try:
        poly_geo = {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[list(coord) for coord in park_poly.exterior.coords]]}, "properties": {"name": PARK_NAME}}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "park_polygon.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [poly_geo]}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

    payload = {
        "type": "FeatureCollection",
        "features": (
            synthetic_points(bench_count, "bench", 11, polygon=park_poly)
            + synthetic_points(tree_count, "tree", 27, polygon=park_poly)
            + synthetic_points(lamp_count, "lamp", 41, polygon=park_poly)
            + synthetic_paths(park_poly)
        ),
    }
    output_path = DATA_DIR / "synthetic_features.geojson"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def load_synthetic_features(path: Path) -> FeatureSet:
    frame = gpd.read_file(path).set_crs("EPSG:4326")
    benches = frame[frame["kind"] == "bench"].copy()
    trees = frame[frame["kind"] == "tree"].copy()
    paths = frame[frame["kind"] == "path"].copy()
    lamps = frame[frame["kind"] == "lamp"].copy()
    return FeatureSet(benches=benches, trees=trees, paths=paths, lamps=lamps)


def overpass_query() -> str:
    return f"""
    [out:json][timeout:30];
    (
      node[amenity=bench]({PARK_BOUNDS['min_lat']},{PARK_BOUNDS['min_lon']},{PARK_BOUNDS['max_lat']},{PARK_BOUNDS['max_lon']});
      node[natural=tree]({PARK_BOUNDS['min_lat']},{PARK_BOUNDS['min_lon']},{PARK_BOUNDS['max_lat']},{PARK_BOUNDS['max_lon']});
      node[highway=street_lamp]({PARK_BOUNDS['min_lat']},{PARK_BOUNDS['min_lon']},{PARK_BOUNDS['max_lat']},{PARK_BOUNDS['max_lon']});
      way[highway~"^(footway|path|pedestrian)$"]({PARK_BOUNDS['min_lat']},{PARK_BOUNDS['min_lon']},{PARK_BOUNDS['max_lat']},{PARK_BOUNDS['max_lon']});
    );
    out body geom;
    """


def fetch_osm_reference() -> Path | None:
    endpoint = "https://overpass-api.de/api/interpreter"
    try:
        response = requests.get(endpoint, params={"data": overpass_query()}, timeout=60)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError):
        return None

    features = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        kind = None
        if tags.get("amenity") == "bench":
            kind = "bench"
        elif tags.get("natural") == "tree":
            kind = "tree"
        elif tags.get("highway") == "street_lamp":
            kind = "lamp"
        elif tags.get("highway") in {"footway", "path", "pedestrian"}:
            kind = "path"

        if kind is None:
            continue

        if element.get("type") == "node":
            lat = element.get("lat")
            lon = element.get("lon")
            if lat is None or lon is None:
                continue
            geometry = {"type": "Point", "coordinates": [lon, lat]}
        elif element.get("type") == "way":
            coords = element.get("geometry")
            if not coords:
                continue
            geometry = {"type": "LineString", "coordinates": [[pt["lon"], pt["lat"]] for pt in coords]}
        else:
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "id": element.get("id"),
                    "kind": kind,
                    "source": "osm",
                    "name": tags.get("name"),
                },
            }
        )

    output_path = DATA_DIR / "osm_reference.geojson"
    output_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def to_projected(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return frame.to_crs(PROJECTED_CRS)


def classify_benches(benches: gpd.GeoDataFrame, trees: gpd.GeoDataFrame, radius: float) -> gpd.GeoDataFrame:
    benches_proj = to_projected(benches)
    trees_proj = to_projected(trees)

    statuses: list[str] = []
    tree_counts: list[int] = []
    for bench_point in benches_proj.geometry:
        count = sum(1 for tree_point in trees_proj.geometry if bench_point.distance(tree_point) <= radius)
        tree_counts.append(count)
        if count == 0:
            statuses.append("sin sombra")
        elif count == 1:
            statuses.append("sombra parcial")
        else:
            statuses.append("bien cubierta")

    result = benches.copy()
    result["tree_count"] = tree_counts
    result["shadow_status"] = statuses
    result["shadow_radius_m"] = radius
    return result


def build_analysis(features: FeatureSet) -> dict[str, gpd.GeoDataFrame]:
    analyses: dict[str, gpd.GeoDataFrame] = {}
    for period, radius in SHADOW_RADII_METERS.items():
        analyses[period] = classify_benches(features.benches, features.trees, radius)
    return analyses


def save_summary(analyses: dict[str, gpd.GeoDataFrame]) -> Path:
    summary = {}
    for period, frame in analyses.items():
        counts = frame["shadow_status"].value_counts().to_dict()
        covered = counts.get("sombra parcial", 0) + counts.get("bien cubierta", 0)
        total = len(frame)
        summary[period] = {
            "label": TIME_LABELS[period],
            "shadow_radius_m": SHADOW_RADII_METERS[period],
            "total_benches": total,
            "coverage_percent": round((covered / total) * 100, 1) if total else 0.0,
            "counts": {
                "sin sombra": counts.get("sin sombra", 0),
                "sombra parcial": counts.get("sombra parcial", 0),
                "bien cubierta": counts.get("bien cubierta", 0),
            },
        }
    output_path = OUTPUT_DIR / "analysis_summary.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def make_circle_style(period: str) -> dict[str, object]:
    return {
        "color": "#4d908e",
        "fillColor": "#4d908e",
        "fillOpacity": 0.08,
        "weight": 1,
        "radius": SHADOW_RADII_METERS[period],
    }


def add_park_boundary(fmap: folium.Map) -> None:
    boundary_path = DATA_DIR / "park_polygon.geojson"
    if not boundary_path.exists():
        return

    folium.GeoJson(
        json.loads(boundary_path.read_text(encoding="utf-8")),
        name="Límite aproximado del parque",
        show=True,
        style_function=lambda _: {
            "color": "#264653",
            "weight": 2,
            "fillOpacity": 0.03,
        },
    ).add_to(fmap)


def add_shadow_circles(group: folium.FeatureGroup, trees: gpd.GeoDataFrame, period: str) -> None:
    style = make_circle_style(period)
    for _, row in trees.iterrows():
        folium.Circle(
            location=[row.geometry.y, row.geometry.x],
            color=style["color"],
            fill=True,
            fill_color=style["fillColor"],
            fill_opacity=style["fillOpacity"],
            weight=style["weight"],
            radius=style["radius"],
            popup=folium.Popup(
                f"Radio de sombra estimado: {style['radius']} m<br>Franja: {TIME_LABELS[period]}",
                max_width=240,
            ),
        ).add_to(group)


def add_bench_markers(group: folium.FeatureGroup, benches: gpd.GeoDataFrame) -> None:
    for _, row in benches.iterrows():
        color = STATUS_COLORS[row["shadow_status"]]
        popup = (
            f"Banca: {row['id']}<br>"
            f"Cobertura: {row['shadow_status']}<br>"
            f"Árboles cercanos: {row['tree_count']}"
        )
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=7,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.92,
            weight=2,
            popup=folium.Popup(popup, max_width=260),
        ).add_to(group)


def add_tree_markers(group: folium.FeatureGroup, trees: gpd.GeoDataFrame) -> None:
    for _, row in trees.iterrows():
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=5,
            color="#2d6a4f",
            fill=True,
            fill_color="#40916c",
            fill_opacity=0.95,
            weight=2,
            popup=folium.Popup(f"Árbol: {row['id']}", max_width=220),
        ).add_to(group)


def add_path_lines(group: folium.FeatureGroup, paths: gpd.GeoDataFrame) -> None:
    for _, row in paths.iterrows():
        if not isinstance(row.geometry, LineString):
            continue
        folium.PolyLine(
            locations=[(lat, lon) for lon, lat in row.geometry.coords],
            color="#577590",
            weight=4,
            opacity=0.82,
            popup=folium.Popup(f"Sendero: {row['id']}", max_width=220),
        ).add_to(group)


def add_lamp_markers(group: folium.FeatureGroup, lamps: gpd.GeoDataFrame) -> None:
    for _, row in lamps.iterrows():
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=4,
            color="#9c6644",
            fill=True,
            fill_color="#f6bd60",
            fill_opacity=0.95,
            weight=2,
            popup=folium.Popup(f"Luminaria: {row['id']}", max_width=220),
        ).add_to(group)


def add_osm_reference_layer(fmap: folium.Map, reference_path: Path | None) -> None:
    if reference_path is None or not reference_path.exists():
        return

    try:
        frame = gpd.read_file(reference_path)
    except Exception:
        return

    if frame.empty:
        return

    group = folium.FeatureGroup(name="Referencia OSM", show=False)
    for _, row in frame.iterrows():
        kind = row.get("kind", "elemento")
        label = {"bench": "Banca", "tree": "Árbol", "lamp": "Luminaria", "path": "Sendero"}.get(kind, "Elemento")
        if isinstance(row.geometry, Point):
            folium.CircleMarker(
                location=[row.geometry.y, row.geometry.x],
                radius=5,
                color="#6c757d",
                fill=True,
                fill_color="#adb5bd",
                fill_opacity=0.8,
                weight=1,
                popup=folium.Popup(f"{label} OSM", max_width=220),
            ).add_to(group)
        elif isinstance(row.geometry, LineString):
            folium.PolyLine(
                locations=[(lat, lon) for lon, lat in row.geometry.coords],
                color="#6c757d",
                weight=3,
                opacity=0.6,
                popup=folium.Popup(f"{label} OSM", max_width=220),
            ).add_to(group)
    group.add_to(fmap)


def add_time_selector(fmap: folium.Map, layer_names: dict[str, dict[str, str]], default_period: str) -> None:
    options_html = "".join(
        f'<option value="{period}"{" selected" if period == default_period else ""}>{TIME_LABELS[period]}</option>'
        for period in layer_names
    )
    layer_js = ",\n".join(
        f"{period}: {{benches: {names['benches']}, shadows: {names['shadows']}}}"
        for period, names in layer_names.items()
    )

    control_html = f"""
    <div id="time-selector-control" style="background: rgba(255,255,255,0.97); padding: 10px 12px; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.18); font-family: Arial, sans-serif; font-size: 13px; min-width: 200px;">
        <div style="font-weight: 700; margin-bottom: 6px;">Franja horaria</div>
        <select id="time-selector-input" style="width: 100%; padding: 6px 8px; border: 1px solid #ccc; border-radius: 8px; background: white;">
            {options_html}
        </select>
        <label style="display:block; margin-top:8px;"><input id="layer-benches-toggle" type="checkbox" checked> Bancas</label>
        <label style="display:block; margin-top:4px;"><input id="layer-shadows-toggle" type="checkbox" checked> Radios de sombra</label>
    </div>
    """

    script = f"""
    (function() {{
        function initializeSelector() {{
        var map = {fmap.get_name()};
        var layers = {{{layer_js}}};
        var activePeriod = "{default_period}";
        var visibility = {{benches: true, shadows: true}};

        function removePeriodLayers() {{
            Object.keys(layers).forEach(function(period) {{
                Object.keys(layers[period]).forEach(function(kind) {{
                    if (map.hasLayer(layers[period][kind])) {{
                        map.removeLayer(layers[period][kind]);
                    }}
                }});
            }});
        }}

        function renderActivePeriod() {{
            Object.keys(layers[activePeriod]).forEach(function(kind) {{
                var layer = layers[activePeriod][kind];
                if (visibility[kind]) {{
                    if (!map.hasLayer(layer)) {{
                        map.addLayer(layer);
                    }}
                }} else if (map.hasLayer(layer)) {{
                    map.removeLayer(layer);
                }}
            }});
        }}

        function setActivePeriod(period) {{
            removePeriodLayers();
            activePeriod = period;
            renderActivePeriod();
        }}

        var control = L.control({{position: 'topright'}});
        control.onAdd = function() {{
            var container = L.DomUtil.create('div');
            container.innerHTML = `{control_html}`;
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);
            return container;
        }};
        control.addTo(map);

        var input = document.getElementById('time-selector-input');
        input.addEventListener('change', function(event) {{
            setActivePeriod(event.target.value);
        }});
        document.getElementById('layer-benches-toggle').addEventListener('change', function(event) {{
            visibility.benches = event.target.checked;
            renderActivePeriod();
        }});
        document.getElementById('layer-shadows-toggle').addEventListener('change', function(event) {{
            visibility.shadows = event.target.checked;
            renderActivePeriod();
        }});

        setActivePeriod(activePeriod);
        window.setActiveParkPeriod = setActivePeriod;
        }}

        if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', initializeSelector);
        }} else {{
            initializeSelector();
        }}
    }})();
    """

    fmap.get_root().script.add_child(folium.Element(script))


def create_map(analyses: dict[str, gpd.GeoDataFrame], features: FeatureSet, reference_path: Path | None) -> Path:
    fmap = folium.Map(location=list(PARK_CENTER), zoom_start=17, tiles="CartoDB positron")
    add_park_boundary(fmap)

    path_group = folium.FeatureGroup(name="Senderos sintéticos", show=True)
    add_path_lines(path_group, features.paths)
    path_group.add_to(fmap)

    lamp_group = folium.FeatureGroup(name="Luminarias sintéticas", show=True)
    add_lamp_markers(lamp_group, features.lamps)
    lamp_group.add_to(fmap)

    tree_group = folium.FeatureGroup(name="Árboles sintéticos", show=True)
    add_tree_markers(tree_group, features.trees)
    tree_group.add_to(fmap)
    add_osm_reference_layer(fmap, reference_path)

    summary_rows = []
    for period, benches in analyses.items():
        counts = benches["shadow_status"].value_counts().to_dict()
        covered = counts.get("sombra parcial", 0) + counts.get("bien cubierta", 0)
        coverage = round((covered / len(benches)) * 100, 1) if len(benches) else 0.0
        summary_rows.append(
            f"<tr><td>{TIME_LABELS[period]}</td><td>{counts.get('sin sombra', 0)}</td><td>{counts.get('sombra parcial', 0)}</td><td>{counts.get('bien cubierta', 0)}</td><td>{coverage}%</td></tr>"
        )

    layer_names: dict[str, dict[str, str]] = {}
    for period, benches in analyses.items():
        shadow_group = folium.FeatureGroup(name=f"Radios de sombra - {TIME_LABELS[period]}", show=period == "morning")
        add_shadow_circles(shadow_group, features.trees, period)
        shadow_group.add_to(fmap)

        bench_group = folium.FeatureGroup(name=f"Bancas - {TIME_LABELS[period]}", show=period == "morning")
        add_bench_markers(bench_group, benches)
        bench_group.add_to(fmap)

        layer_names[period] = {"benches": bench_group.get_name(), "shadows": shadow_group.get_name()}

    summary_html = f"""
    <div style="position: fixed; bottom: 28px; right: 28px; z-index: 9999; width: 330px; background: rgba(255,255,255,0.96); padding: 14px 16px; border-radius: 8px; box-shadow: 0 10px 28px rgba(0,0,0,0.18); font-family: Arial, sans-serif; font-size: 13px; line-height: 1.4;">
        <strong>{PARK_NAME}</strong><br>
        <span style="color:#666; font-size:12px;">PoC con datos sintéticos y referencia OSM opcional</span>
        <hr style="border:0; border-top:1px solid #e5e5e5; margin:10px 0;">
        <strong>Resumen por franja</strong>
        <table style="width:100%; margin-top: 8px; border-collapse: collapse;">
            <thead>
                <tr><th style="text-align:left; border-bottom:1px solid #ddd; padding:4px 0;">Franja</th><th style="text-align:right; border-bottom:1px solid #ddd; padding:4px 0;">Sin</th><th style="text-align:right; border-bottom:1px solid #ddd; padding:4px 0;">Parcial</th><th style="text-align:right; border-bottom:1px solid #ddd; padding:4px 0;">Bien</th><th style="text-align:right; border-bottom:1px solid #ddd; padding:4px 0;">%</th></tr>
            </thead>
            <tbody>
                {{rows}}
            </tbody>
        </table>
    </div>
    """
    summary_html = summary_html.replace("{rows}", "".join(summary_rows))

    legend_html = """
    <div style="position: fixed; bottom: 28px; left: 28px; z-index: 9999; background: white; padding: 14px 16px; border-radius: 8px; box-shadow: 0 8px 24px rgba(0,0,0,0.18); font-family: Arial, sans-serif; font-size: 13px;">
        <strong>Lectura rápida</strong><br>
        <span style="color:#d1495b">●</span> sin sombra<br>
        <span style="color:#f4a261">●</span> sombra parcial<br>
        <span style="color:#2a9d8f">●</span> bien cubierta<br>
        <span style="color:#577590">━</span> sendero sintético<br>
        <span style="color:#f6bd60">●</span> luminaria sintética
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(summary_html))
    fmap.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(collapsed=False).add_to(fmap)
    add_time_selector(fmap, layer_names, default_period="morning")

    output_path = OUTPUT_DIR / "parque_grecia_sombra.html"
    fmap.save(output_path)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prueba de concepto de sombra en bancas del parque central de Grecia.")
    parser.add_argument("--benches", type=int, default=DEFAULT_COUNTS["benches"], help="Cantidad de bancas sintéticas a generar.")
    parser.add_argument("--trees", type=int, default=DEFAULT_COUNTS["trees"], help="Cantidad de árboles sintéticos a generar.")
    parser.add_argument("--lamps", type=int, default=DEFAULT_COUNTS["lamps"], help="Cantidad de luminarias sintéticas a generar.")
    parser.add_argument("--morning-radius", type=float, default=SHADOW_RADII_METERS["morning"], help="Radio de sombra para la mañana, en metros.")
    parser.add_argument("--noon-radius", type=float, default=SHADOW_RADII_METERS["noon"], help="Radio de sombra para el mediodía, en metros.")
    parser.add_argument("--afternoon-radius", type=float, default=SHADOW_RADII_METERS["afternoon"], help="Radio de sombra para la tarde, en metros.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    ensure_dirs()
    SHADOW_RADII_METERS.update({
        "morning": args.morning_radius,
        "noon": args.noon_radius,
        "afternoon": args.afternoon_radius,
    })
    synthetic_path = generate_synthetic_geojson(args.benches, args.trees, args.lamps)
    reference_path = fetch_osm_reference()
    features = load_synthetic_features(synthetic_path)
    analyses = build_analysis(features)
    summary_path = save_summary(analyses)
    output_html = create_map(analyses, features, reference_path)

    report = {
        "park_name": PARK_NAME,
        "synthetic_data": str(synthetic_path),
        "osm_reference": str(reference_path) if reference_path else None,
        "analysis_summary": str(summary_path),
        "output_html": str(output_html),
        "inputs": {
            "benches": args.benches,
            "trees": args.trees,
            "lamps": args.lamps,
            "paths": len(features.paths),
            "shadow_radii_m": SHADOW_RADII_METERS,
        },
        "generated_feature_counts": {
            "benches": len(features.benches),
            "trees": len(features.trees),
            "lamps": len(features.lamps),
            "paths": len(features.paths),
        },
        "scope_note": "Prueba de concepto con datos sintéticos; no sustituye levantamiento de campo ni modelado solar físico.",
    }
    (OUTPUT_DIR / "run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
