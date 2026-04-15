import httpx
import asyncio
from typing import List, Dict
from route_analysis import classify_poi_route_proximity

# ------------------------------------------------------------------
# Kategorie-Definitionen
# Jede Kategorie hat einen Namen und die passenden OSM-Tags.
# OSM nutzt ein Key=Value System: amenity=supermarket bedeutet
# "ein Objekt mit dem Tag amenity dessen Wert supermarket ist".
# Du kannst hier jederzeit neue Kategorien ergÃ¤nzen.
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
# Overpass QL ist die Abfragesprache fÃ¼r OSM-Daten.
# Wir bauen eine einzige groÃŸe Anfrage fÃ¼r alle Kategorien
# und alle StÃ¼tzpunkte gleichzeitig â€” das ist viel effizienter
# als fÃ¼r jeden Punkt eine separate Anfrage zu schicken.
#
# "around:RADIUS,LAT,LON" ist der OSM-Filter fÃ¼r "im Umkreis von"
# ------------------------------------------------------------------
def build_overpass_query(sampled_points: List[Dict], radius: int, categories: List[str]) -> str:
    
    # Nur die gewÃ¤hlten Kategorien abfragen
    active_tags = []
    for cat in categories:
        if cat in POI_CATEGORIES:
            active_tags.extend(POI_CATEGORIES[cat]["tags"])

    # FÃ¼r jeden Tag und jeden Punkt eine Suchzeile bauen
    # OSM kennt zwei Objekttypen die uns interessieren: node (Punkt) und way (FlÃ¤che/GebÃ¤ude)
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
# Weil sich die Suchkreise der StÃ¼tzpunkte Ã¼berlappen,
# wird derselbe Supermarkt oft 3-4x gefunden.
# Wir nutzen OSM-Typ + OSM-ID als eindeutigen SchlÃ¼ssel.
# ------------------------------------------------------------------
def deduplicate_pois(raw_elements: List[Dict]) -> List[Dict]:
    seen_ids = set()
    unique = []

    for el in raw_elements:
        osm_key = (el.get("type"), el.get("id"))
        if osm_key not in seen_ids:
            seen_ids.add(osm_key)
            unique.append(el)

    return unique

# ------------------------------------------------------------------
# OSM-Rohdaten in saubere POI-Objekte umwandeln
# OSM-Elemente kÃ¶nnen "nodes" (haben lat/lon direkt) oder
# "ways" sein (haben ein "center" Objekt mit lat/lon).
# ------------------------------------------------------------------
def parse_poi(element: Dict, route_points: List[Dict]) -> Dict:
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

    detour = classify_poi_route_proximity(route_points, {"lat": lat, "lon": lon})

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
        **detour,
    }


# ------------------------------------------------------------------
# Hauptfunktion: Overpass API aufrufen
# Wir nutzen httpx statt requests weil FastAPI async ist â€”
# mit requests wÃ¼rde der Server wÃ¤hrend der API-Anfrage blockieren.
# ------------------------------------------------------------------
async def fetch_pois_from_osm(
    sampled_points: List[Dict],
    radius: int = 500,
    categories: List[str] = None
) -> List[Dict]:

    if categories is None:
        categories = list(POI_CATEGORIES.keys())

    # Punkte in Batches à 30 aufteilen
    # 30 Punkte × 5 Kategorien = überschaubare Query-Größe
    BATCH_SIZE = 30
    batches = [sampled_points[i:i + BATCH_SIZE] for i in range(0, len(sampled_points), BATCH_SIZE)]

    all_elements = []

    async with httpx.AsyncClient(timeout=90.0) as client:
        for batch in batches:
            query = build_overpass_query(batch, radius, categories)
            try:
                response = await client.post(
                    "https://overpass-api.de/api/interpreter",
                    data={"data": query}
                )
                response.raise_for_status()
                data = response.json()
                all_elements.extend(data.get("elements", []))

                # Kurze Pause zwischen Batches — Overpass fair-use Policy
                await asyncio.sleep(1)

            except httpx.HTTPStatusError as e:
                # Einen fehlgeschlagenen Batch überspringen statt alles abbrechen
                print(f"Batch fehlgeschlagen: {e} — überspringe und mache weiter")
                continue

    unique_elements = deduplicate_pois(all_elements)
    pois = [parse_poi(el, sampled_points) for el in unique_elements]

    return pois