from typing import List, Dict
import xml.etree.ElementTree as ET

# ------------------------------------------------------------------
# Farbe + Icon pro Kategorie (Google Maps KML-Format)
# Farben sind im AABBGGRR Format (Alpha, Blau, Grün, Rot) — 
# das ist KML-spezifisch und andersherum als normales RGB!
# Icons kommen aus dem öffentlichen Google Maps Icon-Set.
# ------------------------------------------------------------------
CATEGORY_STYLES = {
    "supermarket":   {"color": "ff0000ff", "icon": "https://maps.google.com/mapfiles/kml/shapes/shopping.png"},
    "water":         {"color": "ffff0000", "icon": "https://maps.google.com/mapfiles/kml/shapes/water.png"},
    "accommodation": {"color": "ffff6600", "icon": "https://maps.google.com/mapfiles/kml/shapes/lodging.png"},
    "fuel":          {"color": "ff333333", "icon": "https://maps.google.com/mapfiles/kml/shapes/gas_stations.png"},
    "pharmacy":      {"color": "ff00aa00", "icon": "https://maps.google.com/mapfiles/kml/shapes/hospitals.png"},
    "sonstige":      {"color": "ff888888", "icon": "https://maps.google.com/mapfiles/kml/shapes/placemark_circle.png"},
}

DETOUR_TYPE_ORDER = {"direct": 0, "minor": 1, "detour": 2}

def build_description(poi: Dict) -> str:
    # HTML-Tabelle als Popup-Text in Google Maps
    rows = []

    if poi.get("detour_label"):
        rows.append(f"<tr><td><b>Umweg</b></td><td>{poi['detour_label']}</td></tr>")
    if poi.get("opening_hours"):
        rows.append(f"<tr><td><b>Öffnungszeiten</b></td><td>{poi['opening_hours']}</td></tr>")
    if poi.get("phone"):
        rows.append(f"<tr><td><b>Telefon</b></td><td>{poi['phone']}</td></tr>")
    if poi.get("website"):
        rows.append(f"<tr><td><b>Website</b></td><td><a href='{poi['website']}'>{poi['website']}</a></td></tr>")
    if poi.get("brand"):
        rows.append(f"<tr><td><b>Marke</b></td><td>{poi['brand']}</td></tr>")

    if not rows:
        return poi.get("category_label", "")

    return f"<table>{''.join(rows)}</table>"


def generate_kml(pois: List[Dict]) -> str:
    # Wurzel-Element
    kml = ET.Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = ET.SubElement(kml, "Document")
    ET.SubElement(doc, "name").text = "Resupply POIs"
    ET.SubElement(doc, "description").text = f"{len(pois)} POIs"

    # Styles pro Kategorie definieren (Google Maps liest diese für Icons/Farben)
    for cat_key, style_data in CATEGORY_STYLES.items():
        style = ET.SubElement(doc, "Style", id=f"style_{cat_key}")
        icon_style = ET.SubElement(style, "IconStyle")
        ET.SubElement(icon_style, "color").text = style_data["color"]
        ET.SubElement(icon_style, "scale").text = "1.1"
        icon = ET.SubElement(icon_style, "Icon")
        ET.SubElement(icon, "href").text = style_data["icon"]

    # POIs nach Kategorie in Ordner gruppieren
    # Sortierung: direct zuerst, dann minor, dann detour
    folders: Dict[str, List] = {}
    for poi in pois:
        cat = poi.get("category_label", "Sonstiges")
        folders.setdefault(cat, []).append(poi)

    for folder_name, folder_pois in folders.items():
        folder = ET.SubElement(doc, "Folder")
        ET.SubElement(folder, "name").text = folder_name

        # Innerhalb jedes Ordners: direkte POIs zuerst
        sorted_pois = sorted(
            folder_pois,
            key=lambda p: DETOUR_TYPE_ORDER.get(p.get("detour_type", "detour"), DETOUR_TYPE_ORDER["detour"])
        )

        for poi in sorted_pois:
            placemark = ET.SubElement(folder, "Placemark")

            name = poi.get("name", "Unbekannt")
            detour_type = poi.get("detour_type", "")
            prefix = {"direct": "✓", "minor": "~", "detour": "↗"}.get(detour_type, "")
            ET.SubElement(placemark, "name").text = f"{prefix} {name}".strip()

            ET.SubElement(placemark, "description").text = build_description(poi)
            ET.SubElement(placemark, "styleUrl").text = f"#style_{poi.get('category', 'sonstige')}"

            point = ET.SubElement(placemark, "Point")
            ET.SubElement(point, "coordinates").text = f"{poi['lon']},{poi['lat']},0"

    return ET.tostring(kml, encoding="unicode", xml_declaration=False)
