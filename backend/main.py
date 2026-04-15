from fastapi import FastAPI, UploadFile, File, Query, HTTPException
from fastapi.responses import Response
from typing import List, Optional
from uuid import uuid4
import gpxpy
from route_sampling import sample_route
from overpass import fetch_pois_from_osm, POI_CATEGORIES
from kml_export import generate_kml
from route_analysis import DETOUR_TYPE_ORDER

app = FastAPI()
UPLOAD_RESULTS = {}


@app.get("/")
def root():
    return {"message": "Resupply API läuft"}


@app.get("/categories")
def get_categories():
    # Zeigt dem Frontend welche Kategorien verfügbar sind
    return {key: val["label"] for key, val in POI_CATEGORIES.items()}


async def _build_upload_result(
    file: UploadFile,
    interval: float,
    radius: int,
    categories: List[str],
    include_route: bool,
    max_detour: str,
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

    max_level = DETOUR_TYPE_ORDER.get(max_detour, DETOUR_TYPE_ORDER["detour"])
    pois = [
        p for p in pois
        if DETOUR_TYPE_ORDER.get(p.get("detour_type", "detour"), DETOUR_TYPE_ORDER["detour"]) <= max_level
    ]

    route_for_kml = raw_points if include_route else None
    kml_string = generate_kml(pois, route_points=route_for_kml)

    return {
        "pois": pois,
        "missing_route_sections": missing_route_sections,
        "is_complete": len(missing_route_sections) == 0,
        "kml_download": {
            "filename": "resupply.kml",
            "media_type": "application/vnd.google-earth.kml+xml",
            "content": kml_string,
        },
    }


@app.post("/upload")
async def upload_gpx(
    file: UploadFile = File(...),
    interval: float = Query(default=500.0, description="Sampling-Intervall in Metern"),
    radius: int = Query(default=500, description="Suchradius für POIs in Metern"),
    categories: List[str] = Query(default=None, description="POI-Kategorien"),
    include_route: bool = Query(default=True, description="Route als Linie in KML einzeichnen"),
    max_detour: str = Query(default="detour", description="Maximaler Umweg: direct, minor oder detour")
):
    result = await _build_upload_result(
        file=file,
        interval=interval,
        radius=radius,
        categories=categories,
        include_route=include_route,
        max_detour=max_detour,
    )
    upload_id = str(uuid4())
    UPLOAD_RESULTS[upload_id] = result

    return {
        "upload_id": upload_id,
        "pois": result["pois"],
        "missing_route_sections": result["missing_route_sections"],
        "is_complete": result["is_complete"],
    }


@app.post("/export/kml")
async def export_kml(
    file: Optional[UploadFile] = File(default=None),
    interval: float = Query(default=500.0, description="Sampling-Intervall in Metern"),
    radius: int = Query(default=500, description="Suchradius für POIs in Metern"),
    categories: List[str] = Query(default=None, description="POI-Kategorien"),
    include_route: bool = Query(default=True, description="Route als Linie in KML einzeichnen"),
    max_detour: str = Query(default="detour", description="Maximaler Umweg: direct, minor oder detour"),
    upload_id: Optional[str] = Query(default=None, description="Vorherige Upload-ID zur Wiederverwendung des Ergebnisses"),
):
    if upload_id:
        result = UPLOAD_RESULTS.get(upload_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Upload-ID nicht gefunden oder nicht mehr verfügbar")
    else:
        if file is None:
            raise HTTPException(status_code=400, detail="Bitte entweder eine Datei oder eine upload_id angeben")
        result = await _build_upload_result(
            file=file,
            interval=interval,
            radius=radius,
            categories=categories,
            include_route=include_route,
            max_detour=max_detour,
        )

    return Response(
        content=result["kml_download"]["content"],
        media_type=result["kml_download"]["media_type"],
        headers={"Content-Disposition": f"attachment; filename={result['kml_download']['filename']}"},
    )
