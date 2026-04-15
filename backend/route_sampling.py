import math
from typing import List, Dict

# -------------------------------------------------------------------
# Haversine-Formel
# Berechnet die Luftlinien-Distanz zwischen zwei GPS-Koordinaten in Metern.
# Die Erde ist keine perfekte Kugel, aber für Distanzen < 100km ist
# die Haversine-Formel präzise genug (Fehler < 0.5%).
# -------------------------------------------------------------------
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000  # Erdradius in Metern

    # Grad → Radiant umrechnen (math-Funktionen erwarten Radiant)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)

    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c  # Ergebnis in Metern


# -------------------------------------------------------------------
# Linearer Interpolations-Helfer
# Wenn zwei Punkte weiter als `interval` auseinanderliegen,
# berechnen wir den exakten Zwischenpunkt auf der Linie.
# Beispiel: Punkt A bei 0m, Punkt B bei 800m, Interval 500m
# → wir wollen den genauen Punkt bei 500m auf der Strecke A→B
# -------------------------------------------------------------------
def interpolate(lat1: float, lon1: float, lat2: float, lon2: float, fraction: float) -> Dict:
    return {
        "lat": lat1 + (lat2 - lat1) * fraction,
        "lon": lon1 + (lon2 - lon1) * fraction,
    }


# -------------------------------------------------------------------
# Route-Sampling
# Nimmt eine Liste von GPS-Punkten (z.B. 50.000 Stück aus einer GPX)
# und gibt gleichmäßige Stützpunkte alle `interval` Meter zurück.
#
# Warum ist das wichtig?
#   - Komoot/Garmin speichert manchmal alle 5m einen Punkt (bergig)
#     und manchmal alle 100m (flach). Das ist ungleichmäßig.
#   - Für Overpass API wollen wir gleichmäßige Abstände,
#     damit keine Gegend doppelt abgefragt wird.
# -------------------------------------------------------------------
def sample_route(points: List[Dict], interval: float = 500.0) -> List[Dict]:
    if len(points) < 2:
        return points

    sampled = [points[0]]        # Startpunkt immer mitnehmen
    accumulated = 0.0            # Wie weit sind wir seit dem letzten Stützpunkt?

    for i in range(1, len(points)):
        prev = points[i - 1]
        curr = points[i]

        segment_dist = haversine(prev["lat"], prev["lon"], curr["lat"], curr["lon"])

        # Wir arbeiten uns durch das aktuelle Segment vor,
        # bis wir das nächste Interval-Vielfache überschreiten.
        # (Ein langer Segment kann mehrere Stützpunkte enthalten)
        remaining = segment_dist

        while accumulated + remaining >= interval:
            # Wie weit müssen wir noch im Segment gehen bis zum nächsten Punkt?
            needed = interval - accumulated
            fraction = needed / segment_dist  # 0.0 bis 1.0

            new_point = interpolate(prev["lat"], prev["lon"], curr["lat"], curr["lon"], fraction)
            sampled.append(new_point)

            # Jetzt starten wir vom neu eingefügten Punkt weiter
            accumulated = 0.0
            remaining -= needed

        accumulated += remaining

    # Endpunkt immer mitnehmen (wichtig: letztes Resupply vor dem Ziel)
    last_sampled = sampled[-1]
    last_original = points[-1]
    if haversine(last_sampled["lat"], last_sampled["lon"],
                 last_original["lat"], last_original["lon"]) > 10:
        sampled.append(last_original)

    return sampled