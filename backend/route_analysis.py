import math
from typing import Dict, List

DETOUR_TYPE_ORDER = {"direct": 0, "minor": 1, "detour": 2}

DIRECT_DISTANCE_THRESHOLD_METERS = 50.0
MINOR_DISTANCE_THRESHOLD_METERS = 300.0


def _project_to_local_meters(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    lat_scale = 111_320.0
    lon_scale = 111_320.0 * math.cos(math.radians(ref_lat))
    x = (lon - ref_lon) * lon_scale
    y = (lat - ref_lat) * lat_scale
    return x, y


def distance_point_to_segment_meters(point: Dict, start: Dict, end: Dict) -> float:
    ref_lat = (start["lat"] + end["lat"]) / 2
    ref_lon = (start["lon"] + end["lon"]) / 2

    px, py = _project_to_local_meters(point["lat"], point["lon"], ref_lat, ref_lon)
    sx, sy = _project_to_local_meters(start["lat"], start["lon"], ref_lat, ref_lon)
    ex, ey = _project_to_local_meters(end["lat"], end["lon"], ref_lat, ref_lon)

    dx = ex - sx
    dy = ey - sy
    segment_length_sq = dx * dx + dy * dy

    if segment_length_sq == 0:
        return math.hypot(px - sx, py - sy)

    projection = ((px - sx) * dx + (py - sy) * dy) / segment_length_sq
    projection = max(0.0, min(1.0, projection))

    nearest_x = sx + projection * dx
    nearest_y = sy + projection * dy

    return math.hypot(px - nearest_x, py - nearest_y)


def classify_poi_route_proximity(route_points: List[Dict], poi: Dict) -> Dict:
    if len(route_points) < 2:
        return {
            "distance_to_route_meters": None,
            "is_on_route": False,
            "requires_detour": False,
            "estimated_detour_meters": None,
            "detour_meters": None,
            "detour_type": "detour",
            "detour_label": "Umweg erforderlich",
        }

    poi_point = {"lat": poi["lat"], "lon": poi["lon"]}
    min_distance = min(
        distance_point_to_segment_meters(poi_point, route_points[i - 1], route_points[i])
        for i in range(1, len(route_points))
    )
    detour_meters = round(min_distance * 2, 1)

    if min_distance <= DIRECT_DISTANCE_THRESHOLD_METERS:
        detour_type = "direct"
        detour_label = "Direkt an der Route"
    elif min_distance <= MINOR_DISTANCE_THRESHOLD_METERS:
        detour_type = "minor"
        detour_label = f"Kleiner Umweg ({detour_meters} m)"
    else:
        detour_type = "detour"
        detour_label = f"Umweg erforderlich ({detour_meters} m)"

    requires_detour = detour_type != "direct"

    return {
        "distance_to_route_meters": round(min_distance, 1),
        "is_on_route": not requires_detour,
        "requires_detour": requires_detour,
        "estimated_detour_meters": detour_meters,
        "detour_meters": detour_meters,
        "detour_type": detour_type,
        "detour_label": detour_label,
    }
