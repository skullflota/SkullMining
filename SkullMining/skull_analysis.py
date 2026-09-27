"""
Skull Mining - análisis de una sesión de minería en superficie.

Funciones puras (sin EDMC ni red) para poder probarlas fuera del juego.
Entrada: recorrido del Rhino (puntos del Status.json) y refinados (MiningRefined
anclados a la última posición conocida). Salida: resumen con plataformas,
distancias entre ellas, ruta de recogida y métricas de orografía.

Los umbrales marcados con CALIBRAR son provisionales hasta tener datos reales.
"""
from __future__ import annotations

import itertools
import math
import statistics
from typing import Dict, List, Optional, Sequence, Tuple

# Distancia mínima entre plataformas que permite el juego. Confirmada por Carlos (27-sep-2026):
# apurando al máximo en un sitio de Torio, las dos plataformas quedaron a ~47 m.
MIN_RIG_SPACING_M = 47.0
# Dos recogidas a menos de la mitad de esa distancia son la misma plataforma
# (el error de posición llega a ~20 m si el Rhino se mueve mientras refina).
RIG_CLUSTER_RADIUS_M = MIN_RIG_SPACING_M / 2
# Un sitio = zona de un solo mineral de ~50 m como mucho (según Carlos). Plataformas del
# mismo mineral enlazadas a menos de esta distancia forman el mismo sitio.
SITE_LINK_M = 60.0
# Dentro de una recogida los refinados llegan cada 1-2 s (sesión real 27-sep-2026).
BURST_GAP_S = 20.0
# Refinados sueltos del mismo mineral que llegan poco después se suman a la recogida anterior
# (en la sesión real llegó 1 t de torio 58 s después de su recogida).
STRAGGLER_S = 90.0
# 12 chunks por plataforma desde 4.4.1.1 (la sesión real dio 11-12 t por recogida)
MAX_TONNES_PER_COLLECTION = 13
# Velocidad mínima (m/s) para considerar que el Rhino está en movimiento.
MOVING_SPEED_MS = 1.0

Point = Tuple[float, float, float, Optional[float]]  # (t, lat, lon, alt)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float, radius_m: float) -> float:
    """Distancia sobre la superficie de una esfera de radio radius_m."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_m * math.asin(min(1.0, math.sqrt(a)))


def _centroid(pts: Sequence[Tuple[float, float]]) -> Tuple[float, float]:
    # Suficiente para zonas de pocos km; evita problemas en el antimeridiano.
    lat = sum(p[0] for p in pts) / len(pts)
    x = sum(math.cos(math.radians(p[1])) for p in pts)
    y = sum(math.sin(math.radians(p[1])) for p in pts)
    return lat, math.degrees(math.atan2(y, x))


def collections_from_refined(refined: List[dict]) -> List[dict]:
    """Agrupa los refinados en recogidas (pasar el Rhino por una plataforma).

    La posición de la recogida es la del primer refinado, que es cuando el Rhino
    está encima de la plataforma. Los rezagados no mueven la posición.
    """
    raw: List[dict] = []
    for r in sorted(refined, key=lambda x: x["t"]):
        last = raw[-1] if raw else None
        if last and r["t"] - last["end"] <= BURST_GAP_S:
            last["end"] = r["t"]
            last["items"].append(r)
        else:
            raw.append({"start": r["t"], "end": r["t"], "items": [r], "main_type": r["type"],
                        "lat": r.get("lat"), "lon": r.get("lon"), "stragglers": 0})
        c = raw[-1]
        if c["lat"] is None and r.get("lat") is not None:
            c["lat"], c["lon"] = r["lat"], r["lon"]

    # Rezagados: 1-2 t sueltas del mismo mineral poco después de una recogida no llena
    cols: List[dict] = []
    for c in raw:
        prev = cols[-1] if cols else None
        if (prev and len(c["items"]) <= 2 and c["main_type"] == prev["main_type"]
                and c["start"] - prev["end"] <= STRAGGLER_S
                and len(prev["items"]) + len(c["items"]) <= MAX_TONNES_PER_COLLECTION):
            prev["items"] += c["items"]
            prev["end"] = c["end"]
            prev["stragglers"] += len(c["items"])
        else:
            cols.append(c)
    for c in cols:
        counts: Dict[str, int] = {}
        for it in c["items"]:
            counts[it["type"]] = counts.get(it["type"], 0) + 1
        c["types"] = counts
        c["main_type"] = max(counts, key=counts.get)
        c["tonnes"] = len(c["items"])
    return cols


def cluster_rigs(refined: List[dict], radius_m: float, cluster_radius_m: float = RIG_CLUSTER_RADIUS_M) -> List[dict]:
    """Cada plataforma = recogidas en el mismo punto y del mismo mineral principal.

    En la sesión real cada plataforma dio un solo mineral, así que dos plataformas
    cercanas con minerales distintos se cuentan por separado.
    """
    clusters: List[dict] = []
    for col in collections_from_refined(refined):
        if col["lat"] is None:
            continue
        best, best_d = None, None
        for c in clusters:
            if c["main_type"] != col["main_type"]:
                continue
            d = haversine_m(col["lat"], col["lon"], c["lat"], c["lon"], radius_m)
            if d <= cluster_radius_m and (best_d is None or d < best_d):
                best, best_d = c, d
        if best is None:
            best = {"pts": [], "cols": [], "main_type": col["main_type"]}
            clusters.append(best)
        best["pts"].append((col["lat"], col["lon"]))
        best["cols"].append(col)
        best["lat"], best["lon"] = _centroid(best["pts"])

    out = []
    for i, c in enumerate(clusters):
        types: Dict[str, int] = {}
        for col in c["cols"]:
            for k, v in col["types"].items():
                types[k] = types.get(k, 0) + v
        tonnes = sum(col["tonnes"] for col in c["cols"])
        out.append({
            "idx": i + 1,
            "lat": round(c["lat"], 6),
            "lon": round(c["lon"], 6),
            "main_type": c["main_type"],
            "tonnes": tonnes,
            "collections": len(c["cols"]),
            "tonnes_per_collection": round(tonnes / len(c["cols"]), 1),
            "visits": [[col["start"], col["end"]] for col in c["cols"]],
            "first_t": c["cols"][0]["start"],
            "last_t": c["cols"][-1]["end"],
            "types": types,
        })
    return out


def group_sites(rigs: List[dict], radius_m: float, link_m: float = SITE_LINK_M) -> List[dict]:
    """Agrupa plataformas del mismo mineral en sitios (enlace simple a < link_m)."""
    n = len(rigs)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if rigs[i]["main_type"] == rigs[j]["main_type"] and \
                    haversine_m(rigs[i]["lat"], rigs[i]["lon"], rigs[j]["lat"], rigs[j]["lon"], radius_m) <= link_m:
                parent[find(i)] = find(j)
    groups: Dict[int, List[dict]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(rigs[i])
    sites = []
    for k, members in enumerate(sorted(groups.values(), key=lambda g: g[0]["first_t"])):
        lat, lon = _centroid([(r["lat"], r["lon"]) for r in members])
        dists = [haversine_m(a["lat"], a["lon"], b["lat"], b["lon"], radius_m)
                 for a, b in itertools.combinations(members, 2)]
        tonnes = sum(r["tonnes"] for r in members)
        cols = sum(r["collections"] for r in members)
        for r in members:
            r["site"] = k + 1
        sites.append({
            "idx": k + 1,
            "main_type": members[0]["main_type"],
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "rigs": len(members),
            "rig_spacing_min_m": round(min(dists), 1) if dists else None,
            "extent_m": round(max(dists), 1) if dists else 0.0,
            "tonnes": tonnes,
            "collections": cols,
            "tonnes_per_collection": round(tonnes / cols, 1) if cols else None,
        })
    # distancia al sitio más cercano (de cualquier mineral) visitado en la sesión
    for a in sites:
        others = [haversine_m(a["lat"], a["lon"], b["lat"], b["lon"], radius_m) for b in sites if b is not a]
        a["nearest_site_m"] = round(min(others), 1) if others else None
    return sites


def _path_len(order: Sequence[int], dist: List[List[float]], closed: bool) -> float:
    total = sum(dist[a][b] for a, b in zip(order, order[1:]))
    if closed and len(order) > 1:
        total += dist[order[-1]][order[0]]
    return total


def best_route(rigs: List[dict], radius_m: float) -> dict:
    """Ruta más corta que pasa por todas las plataformas (abierta y en circuito)."""
    n = len(rigs)
    if n < 2:
        return {"order": [r["idx"] for r in rigs], "open_m": 0.0, "loop_m": 0.0}
    dist = [[haversine_m(a["lat"], a["lon"], b["lat"], b["lon"], radius_m) for b in rigs] for a in rigs]
    if n <= 8:
        best_open = min(itertools.permutations(range(n)), key=lambda o: _path_len(o, dist, False))
        rest = min(itertools.permutations(range(1, n)), key=lambda o: _path_len((0,) + o, dist, True))
        best_loop = (0,) + rest
    else:  # vecino más cercano
        order, left = [0], set(range(1, n))
        while left:
            nxt = min(left, key=lambda j: dist[order[-1]][j])
            order.append(nxt)
            left.remove(nxt)
        best_open = best_loop = tuple(order)
    return {
        "order": [rigs[i]["idx"] for i in best_loop],
        "open_m": round(_path_len(best_open, dist, False), 1),
        "loop_m": round(_path_len(best_loop, dist, True), 1),
    }


def spacing_stats(rigs: List[dict], radius_m: float) -> dict:
    """Distancia al vecino más cercano de cada plataforma."""
    if len(rigs) < 2:
        return {"nn_min_m": None, "nn_mean_m": None, "max_m": None}
    nn, mx = [], 0.0
    for i, a in enumerate(rigs):
        ds = [haversine_m(a["lat"], a["lon"], b["lat"], b["lon"], radius_m) for j, b in enumerate(rigs) if j != i]
        nn.append(min(ds))
        mx = max(mx, max(ds))
    return {"nn_min_m": round(min(nn), 1), "nn_mean_m": round(statistics.mean(nn), 1), "max_m": round(mx, 1)}


def _track_between(track: List[Point], t0: float, t1: float) -> List[Point]:
    return [p for p in track if t0 <= p[0] <= t1]


def _segment_metrics(pts: List[Point], radius_m: float, use_alt: bool) -> dict:
    path = 0.0
    gain = 0.0
    moving_t = 0.0
    for a, b in zip(pts, pts[1:]):
        d = haversine_m(a[1], a[2], b[1], b[2], radius_m)
        dt = b[0] - a[0]
        path += d
        if dt > 0 and d / dt >= MOVING_SPEED_MS:
            moving_t += dt
        if use_alt and a[3] is not None and b[3] is not None and b[3] > a[3]:
            gain += b[3] - a[3]
    alts = [p[3] for p in pts if p[3] is not None] if use_alt else []
    return {
        "path_m": path,
        "gain_m": gain,
        "moving_s": moving_t,
        "alt_range_m": (max(alts) - min(alts)) if len(alts) >= 2 else None,
    }


def travel_segments(rigs: List[dict], track: List[Point], radius_m: float, use_alt: bool) -> List[dict]:
    """Tramos reales entre recogidas consecutivas (en el orden en que se hicieron)."""
    visits = []
    for r in rigs:
        for v0, v1 in r.get("visits", [[r["first_t"], r["last_t"]]]):
            visits.append((v0, v1, r))
    visits.sort(key=lambda v: v[0])
    segs = []
    for (_, t_start, ra), (tb, _, rb) in zip(visits, visits[1:]):
        if ra is rb or tb <= t_start:
            continue
        pts = _track_between(track, t_start, tb)
        straight = haversine_m(ra["lat"], ra["lon"], rb["lat"], rb["lon"], radius_m)
        if len(pts) < 2 or straight < 1:
            continue
        m = _segment_metrics(pts, radius_m, use_alt)
        # tiempo en movimiento: descarta esperas paradas entre vueltas de recogida
        dt = m["moving_s"] if m["moving_s"] > 0 else tb - t_start
        segs.append({
            "from": ra["idx"],
            "to": rb["idx"],
            "straight_m": round(straight, 1),
            "path_m": round(m["path_m"], 1),
            "time_s": round(dt, 1),
            "eff_speed_ms": round(straight / dt, 2) if dt > 0 else None,
            "sinuosity": round(m["path_m"] / straight, 2) if straight > 0 else None,
            "gain_m": round(m["gain_m"], 1) if use_alt else None,
        })
    return segs


def classify_terrain(sinuosity: Optional[float], gain_per_km: Optional[float], moving_speed: Optional[float]) -> str:
    """Etiqueta provisional. CALIBRAR con sesiones reales de la flota."""
    if sinuosity is None and gain_per_km is None and moving_speed is None:
        return "sin datos"
    score = 0
    if sinuosity is not None:
        score += 2 if sinuosity > 1.4 else (1 if sinuosity > 1.15 else 0)
    if gain_per_km is not None:
        score += 2 if gain_per_km > 60 else (1 if gain_per_km > 20 else 0)
    if moving_speed is not None:
        score += 2 if moving_speed < 8 else (1 if moving_speed < 14 else 0)
    if score <= 1:
        return "llano"
    if score <= 3:
        return "ondulado"
    return "montañoso"


def summarize(session: dict) -> dict:
    """Resumen completo de una sesión. `session` sale de SurfaceSession.to_dict()."""
    radius = session.get("planet_radius") or 0.0
    track: List[Point] = [tuple(p) for p in session.get("track", [])]  # type: ignore
    refined = session.get("refined", [])
    use_alt = bool(session.get("alt_from_avg_radius"))

    if radius <= 0:
        return {"error": "sin radio de planeta"}

    rigs = cluster_rigs(refined, radius)
    sites = group_sites(rigs, radius)
    route = best_route(rigs, radius)
    spacing = spacing_stats(rigs, radius)
    segs = travel_segments(rigs, track, radius, use_alt)
    whole = _segment_metrics(track, radius, use_alt) if len(track) >= 2 else None

    sinuosities = [s["sinuosity"] for s in segs if s["sinuosity"]]
    eff_speeds = [s["eff_speed_ms"] for s in segs if s["eff_speed_ms"]]
    sinuosity = round(statistics.median(sinuosities), 2) if sinuosities else None
    eff_speed = round(statistics.median(eff_speeds), 2) if eff_speeds else None

    gain_per_km = None
    moving_speed = None
    if whole and whole["path_m"] > 50:
        if use_alt:
            gain_per_km = round(whole["gain_m"] / (whole["path_m"] / 1000), 1)
        if whole["moving_s"] > 0:
            moving_speed = round(whole["path_m"] / whole["moving_s"], 2)

    tonnes_by_type: Dict[str, int] = {}
    for r in refined:
        tonnes_by_type[r["type"]] = tonnes_by_type.get(r["type"], 0) + 1
    names = {r["type"]: r.get("name") or r["type"] for r in refined}

    t_first = track[0][0] if track else (refined[0]["t"] if refined else session.get("start_t", 0))
    t_last_ref = max((r["t"] for r in refined), default=None)
    duration = (t_last_ref - t_first) if t_last_ref else 0

    # Tiempo entre recogidas de una misma plataforma (ritmo real de la vuelta)
    cycles = []
    for r in rigs:
        vs = r["visits"]
        cycles += [b[0] - a[0] for a, b in zip(vs, vs[1:])]
    cycle_s = round(statistics.median(cycles), 1) if cycles else None
    per_col = [r["tonnes_per_collection"] for r in rigs]
    tpc = round(statistics.median(per_col), 1) if per_col else None

    centroid = _centroid([(r["lat"], r["lon"]) for r in rigs]) if rigs else (
        _centroid([(p[1], p[2]) for p in track]) if track else (None, None))

    return {
        "rigs": len(rigs),
        "rig_list": rigs,
        "sites": sites,
        "collections": sum(r["collections"] for r in rigs),
        "tonnes_per_collection": tpc,
        "cycle_s_median": cycle_s,
        "route": route,
        "spacing": spacing,
        "segments": segs,
        "sinuosity_median": sinuosity,
        "eff_speed_median_ms": eff_speed,
        "moving_speed_ms": moving_speed,
        "gain_per_km": gain_per_km,
        "alt_range_m": round(whole["alt_range_m"], 1) if whole and whole["alt_range_m"] is not None else None,
        "track_len_m": round(whole["path_m"], 1) if whole else 0,
        "terrain": classify_terrain(sinuosity, gain_per_km, moving_speed or eff_speed),
        "tonnes": sum(tonnes_by_type.values()),
        "tonnes_by_type": tonnes_by_type,
        "type_names": names,
        "duration_s": round(duration, 1),
        "center_lat": round(centroid[0], 6) if centroid[0] is not None else None,
        "center_lon": round(centroid[1], 6) if centroid[1] is not None else None,
    }


def downsample(track: List[Point], max_points: int = 1500) -> List[Point]:
    if len(track) <= max_points:
        return track
    step = len(track) / max_points
    out = [track[int(i * step)] for i in range(max_points)]
    if out[-1] != track[-1]:
        out[-1] = track[-1]
    return out


def encode_track(track: List[Point], t0: float) -> str:
    """Formato compacto 't,lat,lon,alt;...' con t en segundos desde el inicio."""
    parts = []
    for t, lat, lon, alt in track:
        a = "" if alt is None else f"{alt:.1f}"
        parts.append(f"{int(round(t - t0))},{lat:.6f},{lon:.6f},{a}")
    return ";".join(parts)
