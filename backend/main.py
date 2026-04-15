from fastapi import FastAPI, UploadFile, File, Query
from typing import List
import gpxpy
from route_sampling import sample_route
from route_analysis import classify_poi_route_proximity
from overpass import fetch_pois_from_osm, POI_CATEGORIES

app = FastAPI()


@app.get("/")
def root():
    return {"message": "Resupply API lÃ¤uft"}


@app.get("/categories")
def get_categories():
    # Zeigt dem Frontend welche Kategorien verfÃ¼gbar sind
    return {key: val["label"] for key, val in POI_CATEGORIES.items()}


@app.post("/upload")
async def upload_gpx(
    file: UploadFile = File(...),
    interval: float = Query(default=500.0, description="Sampling-Intervall in Metern"),
    radius: int = Query(default=500, description="Suchradius fÃ¼r POIs in Metern"),
    categories: List[str] = Query(default=None, description="POI-Kategorien, z.B. supermarket,water"),
    direct_route_threshold: float = Query(
        default=75.0,
        description="Maximale Distanz zur Route in Metern, damit ein POI als direkt an der Route gilt"
    )
):
    content = await file.read()
    gpx = gpxpy.parse(content.decode("utf-8"))

    raw_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                raw_points.append({"lat": p.latitude, "lon": p.longitude})

    if not raw_points:
        return {"error": "Keine Punkte in der GPX-Datei gefunden"}

    sampled = sample_route(raw_points, interval=interval)
    pois = await fetch_pois_from_osm(sampled, radius=radius, categories=categories)
    pois = [
        {
            **poi,
            **classify_poi_route_proximity(
                raw_points,
                poi,
                direct_route_threshold=direct_route_threshold
            ),
        }
        for poi in pois
    ]

    # POIs nach Kategorie gruppieren fÃ¼r Ã¼bersichtliche Ausgabe
    by_category = {}
    for poi in pois:
        cat = poi["category_label"]
        by_category.setdefault(cat, []).append(poi)

    return {
        "raw_points_count": len(raw_points),
        "sampled_points_count": len(sampled),
        "interval_meters": interval,
        "radius_meters": radius,
        "direct_route_threshold_meters": direct_route_threshold,
        "total_pois_found": len(pois),
        "by_category": {cat: len(items) for cat, items in by_category.items()},
        "pois": pois
    }
