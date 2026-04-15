from fastapi import FastAPI, UploadFile, File, Query
from fastapi.responses import Response
from typing import List
import gpxpy
from route_sampling import sample_route
from overpass import fetch_pois_from_osm, POI_CATEGORIES
from kml_export import generate_kml
from route_analysis import DETOUR_TYPE_ORDER

app = FastAPI()


@app.get("/")
def root():
    return {"message": "Resupply API läuft"}


@app.get("/categories")
def get_categories():
    # Zeigt dem Frontend welche Kategorien verfügbar sind
    return {key: val["label"] for key, val in POI_CATEGORIES.items()}


@app.post("/upload")
async def upload_gpx(
    file: UploadFile = File(...),
    interval: float = Query(default=500.0, description="Sampling-Intervall in Metern"),
    radius: int = Query(default=500, description="Suchradius für POIs in Metern"),
    categories: List[str] = Query(default=None, description="POI-Kategorien"),
    export: str = Query(default="both", description="Ausgabeformat: json, kml oder both"),
    include_route: bool = Query(default=True, description="Route als Linie in KML einzeichnen"),
    max_detour: str = Query(default="detour", description="Maximaler Umweg: direct, minor oder detour")
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
    fetch_result = await fetch_pois_from_osm(sampled, raw_points, radius=radius, categories=categories)
    pois = fetch_result["pois"]

    # Umweg-Filter anwenden
    max_level = DETOUR_TYPE_ORDER.get(max_detour, DETOUR_TYPE_ORDER["detour"])
    pois = [
        p for p in pois
        if DETOUR_TYPE_ORDER.get(p.get("detour_type", "detour"), DETOUR_TYPE_ORDER["detour"]) <= max_level
    ]

    route_for_kml = raw_points if include_route else None
    kml_string = generate_kml(pois, route_points=route_for_kml)

    if export == "kml":
        return Response(
            content=kml_string,
            media_type="application/vnd.google-earth.kml+xml",
            headers={"Content-Disposition": "attachment; filename=resupply.kml"}
        )

    failed_batches = [
        batch for batch in fetch_result["batch_reports"]
        if batch["status"] == "failed"
    ]

    by_category = {}
    for poi in pois:
        cat = poi["category_label"]
        by_category.setdefault(cat, []).append(poi)

    return {
        "raw_points_count": len(raw_points),
        "sampled_points_count": len(sampled),
        "interval_meters": interval,
        "radius_meters": radius,
        "batch_summary": {
            "total_batches": fetch_result["total_batches"],
            "successful_batches_count": fetch_result["successful_batches_count"],
            "failed_batches_count": fetch_result["failed_batches_count"],
            "is_complete": fetch_result["failed_batches_count"] == 0,
        },
        "failed_batches": failed_batches,
        "total_pois_found": len(pois),
        "by_category": {cat: len(items) for cat, items in by_category.items()},
        "pois": pois,
        "kml_export": {
            "filename": "resupply.kml",
            "media_type": "application/vnd.google-earth.kml+xml",
            "content": kml_string,
        } if export == "both" else None,
    }
