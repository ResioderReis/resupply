from pathlib import Path
from uuid import uuid4

import gpxpy
from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.responses import FileResponse
from typing import List

from kml_export import generate_kml
from overpass import fetch_pois_from_osm, POI_CATEGORIES
from route_analysis import DETOUR_TYPE_ORDER
from route_sampling import sample_route

app = FastAPI()
KML_EXPORT_DIR = Path(__file__).resolve().parent / "tmp_exports"
KML_EXPORT_DIR.mkdir(exist_ok=True)


@app.get("/")
def root():
    return {"message": "Resupply API läuft"}


@app.get("/categories")
def get_categories():
    return {key: val["label"] for key, val in POI_CATEGORIES.items()}


def save_kml_tempfile(kml_content: str, filename: str = "resupply.kml") -> dict:
    file_id = str(uuid4())
    file_path = KML_EXPORT_DIR / f"{file_id}.kml"
    file_path.write_text(kml_content, encoding="utf-8")
    return {
        "file_id": file_id,
        "filename": filename,
        "download_url": f"/download/{file_id}",
    }


async def analyze_route(file: UploadFile, params: dict) -> dict:
    content = await file.read()
    gpx = gpxpy.parse(content.decode("utf-8"))

    raw_points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for p in segment.points:
                raw_points.append({"lat": p.latitude, "lon": p.longitude})

    if not raw_points:
        return {"error": "Keine Punkte in der GPX-Datei gefunden"}

    sampled = sample_route(raw_points, interval=params["interval"])
    fetch_result = await fetch_pois_from_osm(
        sampled,
        raw_points,
        radius=params["radius"],
        categories=params["categories"],
    )

    pois = fetch_result["pois"]
    missing_route_sections = [
        {
            "batch_id": batch["batch_id"],
            "start_coordinate": batch["start_coordinate"],
            "end_coordinate": batch["end_coordinate"],
            "bounding_box": batch["bounding_box"],
        }
        for batch in fetch_result["batch_reports"]
        if batch["status"] == "failed"
    ]

    max_level = DETOUR_TYPE_ORDER.get(params["max_detour"], DETOUR_TYPE_ORDER["detour"])
    pois = [
        poi for poi in pois
        if DETOUR_TYPE_ORDER.get(poi.get("detour_type", "detour"), DETOUR_TYPE_ORDER["detour"]) <= max_level
    ]

    kml_content = generate_kml(pois)
    kml_file = save_kml_tempfile(kml_content)

    return {
        "pois": pois,
        "summary": {
            "raw_points_count": len(raw_points),
            "sampled_points_count": len(sampled),
            "total_pois": len(pois),
            "is_complete": len(missing_route_sections) == 0,
            "missing_route_sections_count": len(missing_route_sections),
            "coverage_percent": fetch_result["coverage_percent"],
            "total_batches": fetch_result["total_batches"],
            "successful_batches": fetch_result["successful_batches_count"],
            "failed_batches": fetch_result["failed_batches_count"],
            "missing_route_sections": missing_route_sections,
        },
        "kml_download_url": kml_file["download_url"],
    }


@app.post("/analyze")
async def analyze_gpx(
    file: UploadFile = File(...),
    interval: float = Query(default=500.0, description="Sampling-Intervall in Metern"),
    radius: int = Query(default=500, description="Suchradius für POIs in Metern"),
    categories: List[str] = Query(default=None, description="POI-Kategorien"),
    max_detour: str = Query(default="detour", description="Maximaler Umweg: direct, minor oder detour"),
):
    params = {
        "interval": interval,
        "radius": radius,
        "categories": categories,
        "max_detour": max_detour,
    }
    return await analyze_route(file, params)


@app.get("/download/{file_id}")
def download_kml(file_id: str):
    file_path = KML_EXPORT_DIR / f"{file_id}.kml"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")

    return FileResponse(
        path=file_path,
        media_type="application/vnd.google-earth.kml+xml",
        filename="resupply.kml",
        headers={"Content-Disposition": 'attachment; filename="resupply.kml"'},
    )
