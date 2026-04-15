from fastapi import FastAPI, UploadFile, File, Query
from typing import List
import gpxpy
from route_sampling import sample_route
from overpass import fetch_pois_from_osm, POI_CATEGORIES

app = FastAPI()


@app.get("/")
def root():
    return {"message": "Resupply API läuft 🚀"}


@app.get("/categories")
def get_categories():
    # Zeigt dem Frontend welche Kategorien verfügbar sind
    return {key: val["label"] for key, val in POI_CATEGORIES.items()}


@app.post("/upload")
async def upload_gpx(
    file: UploadFile = File(...),
    interval: float = Query(default=500.0, description="Sampling-Intervall in Metern"),
    radius: int = Query(default=500, description="Suchradius für POIs in Metern"),
    categories: List[str] = Query(default=None, description="POI-Kategorien, z.B. supermarket,water")
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

    # POIs nach Kategorie gruppieren für übersichtliche Ausgabe
    by_category = {}
    for poi in pois:
        cat = poi["category_label"]
        by_category.setdefault(cat, []).append(poi)

    return {
        "raw_points_count": len(raw_points),
        "sampled_points_count": len(sampled),
        "interval_meters": interval,
        "radius_meters": radius,
        "total_pois_found": len(pois),
        "by_category": {cat: len(items) for cat, items in by_category.items()},
        "pois": pois
    }