import asyncio
import httpx
import logging
from typing import List, Dict
from route_analysis import classify_poi_route_proximity

logger = logging.getLogger(__name__)

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
]

DEFAULT_BATCH_SIZE = 20
MAX_RETRIES_PER_BATCH = 2
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _get_batch_bounds(batch: List[Dict]) -> Dict:
    lats = [point["lat"] for point in batch]
    lons = [point["lon"] for point in batch]
    return {
        "min_lat": min(lats),
        "min_lon": min(lons),
        "max_lat": max(lats),
        "max_lon": max(lons),
    }

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
            batch_id = f"batch-{batch_index}"
            start_point = batch[0]
            end_point = batch[-1]
            bounding_box = _get_batch_bounds(batch)
            poi_count = 0

            logger.info(
                "Starting %s start=%s end=%s bbox=%s",
                batch_id,
                start_point,
                end_point,
                bounding_box,
            )

            for attempt in range(1, MAX_RETRIES_PER_BATCH + 1):
                for overpass_url in OVERPASS_URLS:
                    try:
                        response = await client.post(overpass_url, data={"data": query})
                        response.raise_for_status()
                        data = response.json()
                        batch_elements = data.get("elements", [])
                        poi_count = len(batch_elements)
                        all_elements.extend(batch_elements)
                        batch_successful = True
                        successful_url = overpass_url
                        logger.info(
                            "Batch success %s endpoint=%s pois=%s",
                            batch_id,
                            overpass_url,
                            poi_count,
                        )
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
                            logger.warning(
                                "Batch failed %s endpoint=%s status=%s retry=false error=%s",
                                batch_id,
                                overpass_url,
                                status_code,
                                e,
                            )
                            break

                        logger.warning(
                            "Batch failed %s endpoint=%s attempt=%s/%s status=%s error=%s",
                            batch_id,
                            overpass_url,
                            attempt,
                            MAX_RETRIES_PER_BATCH,
                            status_code,
                            e,
                        )
                    except httpx.HTTPError as e:
                        batch_errors.append({
                            "attempt": attempt,
                            "url": overpass_url,
                            "status_code": None,
                            "message": str(e),
                        })
                        logger.warning(
                            "Batch failed %s endpoint=%s attempt=%s/%s error=%s",
                            batch_id,
                            overpass_url,
                            attempt,
                            MAX_RETRIES_PER_BATCH,
                            e,
                        )

                if batch_successful:
                    break

                await asyncio.sleep(attempt)

            batch_report = {
                "batch_id": batch_id,
                "batch_index": batch_index,
                "batch_size": len(batch),
                "status": "success" if batch_successful else "failed",
                "start_coordinate": start_point,
                "end_coordinate": end_point,
                "bounding_box": bounding_box,
                "poi_count": poi_count,
                "successful_url": successful_url,
                "errors": batch_errors,
            }
            batch_reports.append(batch_report)

            if not batch_successful:
                logger.warning("Batch failed permanently %s", batch_id)
                continue

            await asyncio.sleep(1)

    unique_elements = deduplicate_pois(all_elements)
    pois = [parse_poi(el, route_points) for el in unique_elements]
    failed_batches_count = sum(1 for batch in batch_reports if batch["status"] == "failed")
    successful_batches_count = sum(1 for batch in batch_reports if batch["status"] == "success")
    total_batches = len(batch_reports)
    coverage_percent = round((successful_batches_count / total_batches) * 100, 1) if total_batches else 100.0

    return {
        "pois": pois,
        "batch_reports": batch_reports,
        "failed_batches_count": failed_batches_count,
        "successful_batches_count": successful_batches_count,
        "total_batches": total_batches,
        "coverage_percent": coverage_percent,
    }
