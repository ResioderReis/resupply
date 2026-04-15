import httpx
from route_sampling import haversine
from typing import List, Dict

# ------------------------------------------------------------------
# Kategorie-Definitionen
# Jede Kategorie hat einen Namen und die passenden OSM-Tags.
# OSM nutzt ein Key=Value System: amenity=supermarket bedeutet
# "ein Objekt mit dem Tag amenity dessen Wert supermarket ist".
# Du kannst hier jederzeit neue Kategorien ergänzen.
# ------------------------------------------------------------------
POI_CATEGORIES = {
    "supermarket": {
        "label": "Supermarkt",
        "tags": [("amenity", "supermarket"), ("shop", "supermarket"), ("shop", "convenience")]
    },
    "water": {
        "label": "Wasserquelle",
        "tags": [("amenity", "drinking_water"), ("amenity", "water_point")]
    },
    "accommodation": {
        "label": "Unterkunft",
        "tags": [("tourism", "hotel"), ("tourism", "hostel"), ("tourism", "guest_house"), ("tourism", "camp_site")]
    },
    "fuel": {
        "label": "Tankstelle",
        "tags": [("amenity", "fuel")]
    },
    "pharmacy": {
        "label": "Apotheke",
        "tags": [("amenity", "pharmacy")]
    },
}


# ------------------------------------------------------------------
# Overpass Query bauen
# Overpass QL ist die Abfragesprache für OSM-Daten.
# Wir bauen eine einzige große Anfrage für alle Kategorien
# und alle Stützpunkte gleichzeitig — das ist viel effizienter
# als für jeden Punkt eine separate Anfrage zu schicken.
#
# "around:RADIUS,LAT,LON" ist der OSM-Filter für "im Umkreis von"
# ------------------------------------------------------------------
def build_overpass_query(sampled_points: List[Dict], radius: int, categories: List[str]) -> str:
    
    # Nur die gewählten Kategorien abfragen
    active_tags = []
    for cat in categories:
        if cat in POI_CATEGORIES:
            active_tags.extend(POI_CATEGORIES[cat]["tags"])

    # Für jeden Tag und jeden Punkt eine Suchzeile bauen
    # OSM kennt zwei Objekttypen die uns interessieren: node (Punkt) und way (Fläche/Gebäude)
    lines = []
    for key, value in active_tags:
        for point in sampled_points:
            lat = point["lat"]
            lon = point["lon"]
            lines.append(f'  node["{key}"="{value}"](around:{radius},{lat},{lon});')
            lines.append(f'  way["{key}"="{value}"](around:{radius},{lat},{lon});')

    query_body = "\n".join(lines)

    return f"""
[out:json][timeout:60];
(
{query_body}
);
out center tags;
"""


# ------------------------------------------------------------------
# Deduplizierung
# Weil sich die Suchkreise der Stützpunkte überlappen,
# wird derselbe Supermarkt oft 3-4x gefunden.
# Wir nutzen die OSM-ID als eindeutigen Schlüssel.
# ------------------------------------------------------------------
def deduplicate_pois(raw_elements: List[Dict]) -> List[Dict]:
    seen_ids = set()
    unique = []

    for el in raw_elements:
        osm_id = el.get("id")
        if osm_id not in seen_ids:
            seen_ids.add(osm_id)
            unique.append(el)

    return unique

# ------------------------------------------------------------------
# Umweg-Berechnung
# Findet den nächsten Routenpunkt zum POI und klassifiziert
# ob der POI direkt anliegt oder einen Umweg erfordert.
# Umweg = Luftlinie zum nächsten Routenpunkt × 2 (hin und zurück)
# ------------------------------------------------------------------
def calculate_detour(poi_lat: float, poi_lon: float, sampled_points: List[Dict]) -> Dict:
    min_distance = float("inf")

    for point in sampled_points:
        dist = haversine(poi_lat, poi_lon, point["lat"], point["lon"])
        if dist < min_distance:
            min_distance = dist

    detour_meters = round(min_distance * 2)  # hin + zurück

    if min_distance <= 50:
        detour_type = "direct"
        detour_label = "Direkt an der Route"
    elif min_distance <= 300:
        detour_type = "minor"
        detour_label = f"Kleiner Umweg ({detour_meters}m)"
    else:
        detour_type = "detour"
        detour_label = f"Umweg erforderlich ({detour_meters}m)"

    return {
        "detour_meters": detour_meters,
        "detour_type": detour_type,
        "detour_label": detour_label,
    }

# ------------------------------------------------------------------
# OSM-Rohdaten in saubere POI-Objekte umwandeln
# OSM-Elemente können "nodes" (haben lat/lon direkt) oder
# "ways" sein (haben ein "center" Objekt mit lat/lon).
# ------------------------------------------------------------------
def parse_poi(element: Dict, sampled_points: List[Dict]) -> Dict:
    tags = element.get("tags", {})

    if element["type"] == "node":
        lat = element["lat"]
        lon = element["lon"]
    else:
        lat = element["center"]["lat"]
        lon = element["center"]["lon"]

    category = "sonstige"
    category_label = "Sonstiges"
    for cat_key, cat_data in POI_CATEGORIES.items():
        for tag_key, tag_value in cat_data["tags"]:
            if tags.get(tag_key) == tag_value:
                category = cat_key
                category_label = cat_data["label"]
                break

    detour = calculate_detour(lat, lon, sampled_points)

    return {
        "osm_id": element["id"],
        "osm_type": element["type"],
        "name": tags.get("name", "Unbekannt"),
        "category": category,
        "category_label": category_label,
        "lat": lat,
        "lon": lon,
        "opening_hours": tags.get("opening_hours"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "website": tags.get("website") or tags.get("contact:website"),
        "brand": tags.get("brand"),
        **detour,  # detour_meters, detour_type, detour_label werden hier eingefügt
    }


# ------------------------------------------------------------------
# Hauptfunktion: Overpass API aufrufen
# Wir nutzen httpx statt requests weil FastAPI async ist —
# mit requests würde der Server während der API-Anfrage blockieren.
# ------------------------------------------------------------------
async def fetch_pois_from_osm(
    sampled_points: List[Dict],
    radius: int = 500,
    categories: List[str] = None
) -> List[Dict]:

    if categories is None:
        categories = list(POI_CATEGORIES.keys())  # alle Kategorien

    query = build_overpass_query(sampled_points, radius, categories)

    # Overpass hat mehrere öffentliche Server — wir nehmen den deutschen
    overpass_url = "https://overpass-api.de/api/interpreter"

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(overpass_url, data={"data": query})
        response.raise_for_status()
        data = response.json()

    raw_elements = data.get("elements", [])
    unique_elements = deduplicate_pois(raw_elements)
    pois = [parse_poi(el, sampled_points) for el in unique_elements]

    return pois