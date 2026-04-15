import asyncio
import httpx
from typing import List, Dict
from route_analysis import classify_poi_route_proximity

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

DEFAULT_BATCH_SIZE = 20
MAX_RETRIES_PER_BATCH = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

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
# und alle Stützpunkte gleichzeitig. Das ist viel effizienter
# als für jeden Punkt eine separate Anfrage zu schicken.
#
# "around:RADIUS,LAT,LON" ist der OSM-Filter für "im Umkreis von"
# ------------------------------------------------------------------
def build_overpass_query(sampled_points: List[Dict], radius: int, categories: List[str]) -> str:
    active_tags = []
    for cat in categories:
        if cat in POI_CATEGORIES:
            active_tags.extend(POI_CATEGORIES[cat]["tags"])

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
# Wir nutzen OSM-Typ + OSM-ID als eindeutigen Schlüssel.
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
# OSM-Elemente können "nodes" mit lat/lon direkt oder
# "ways" mit einem "center"-Objekt sein.
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
# Wir nutzen httpx statt requests weil FastAPI async ist.
# Mit requests würde der Server während der API-Anfrage blockieren.
# ------------------------------------------------------------------
async def fetch_pois_from_osm(
    sampled_points: List[Dict],
    route_points: List[Dict],
    radius: int = 500,
    categories: List[str] = None
) -> Dict:
    if categories is None:
        categories = list(POI_CATEGORIES.keys())

    batches = [
        sampled_points[i:i + DEFAULT_BATCH_SIZE]
        for i in range(0, len(sampled_points), DEFAULT_BATCH_SIZE)
    ]

    all_elements = []
    batch_reports = []

    async with httpx.AsyncClient(timeout=90.0) as client:
        for batch_index, batch in enumerate(batches, start=1):
            query = build_overpass_query(batch, radius, categories)
            batch_successful = False
            batch_errors = []
            successful_url = None

            for attempt in range(1, MAX_RETRIES_PER_BATCH + 1):
                for overpass_url in OVERPASS_URLS:
                    try:
                        response = await client.post(overpass_url, data={"data": query})
                        response.raise_for_status()
                        data = response.json()
                        all_elements.extend(data.get("elements", []))
                        batch_successful = True
                        successful_url = overpass_url
                        break
                    except httpx.HTTPStatusError as e:
                        status_code = e.response.status_code
                        error_info = {
                            "attempt": attempt,
                            "url": overpass_url,
                            "status_code": status_code,
                            "message": str(e),
                        }
                        batch_errors.append(error_info)

                        if status_code not in RETRYABLE_STATUS_CODES:
                            print(f"Batch fehlgeschlagen: {e} - nicht erneut versuchen")
                            break

                        print(
                            f"Batch fehlgeschlagen auf {overpass_url} "
                            f"(Versuch {attempt}/{MAX_RETRIES_PER_BATCH}): {e}"
                        )
                    except httpx.HTTPError as e:
                        batch_errors.append({
                            "attempt": attempt,
                            "url": overpass_url,
                            "status_code": None,
                            "message": str(e),
                        })
                        print(
                            f"Batch fehlgeschlagen auf {overpass_url} "
                            f"(Versuch {attempt}/{MAX_RETRIES_PER_BATCH}): {e}"
                        )

                if batch_successful:
                    break

                await asyncio.sleep(attempt)

            batch_report = {
                "batch_index": batch_index,
                "batch_size": len(batch),
                "status": "ok" if batch_successful else "failed",
                "sampled_points": batch,
                "successful_url": successful_url,
                "errors": batch_errors,
            }
            batch_reports.append(batch_report)

            if not batch_successful:
                print("Batch endgültig fehlgeschlagen - überspringe und mache weiter")
                continue

            await asyncio.sleep(1)

    unique_elements = deduplicate_pois(all_elements)
    pois = [parse_poi(el, route_points) for el in unique_elements]
    failed_batches_count = sum(1 for batch in batch_reports if batch["status"] == "failed")
    successful_batches_count = sum(1 for batch in batch_reports if batch["status"] == "ok")

    return {
        "pois": pois,
        "batch_reports": batch_reports,
        "failed_batches_count": failed_batches_count,
        "successful_batches_count": successful_batches_count,
        "total_batches": len(batch_reports),
    }
