"""
Skull Mining - sitios de la flota en el planeta actual, para el minimapa (v0.9.0).

Descarga de la hoja los sitios del cuerpo donde estás (con tu CMDR y la clave de la flota) y calcula
lo que hay que dibujar: distancia y rumbo a cada sitio, el objetivo y la escala del mapa.
Sin Tk: se puede probar fuera de EDMC.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Callable, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

REFRESH_S = 300            # volver a pedir los sitios del cuerpo cada 5 min
RETRY_S = 60               # si falla, reintentar al minuto
SCALES_M = (250, 500, 1000, 2000, 5000, 10000, 25000, 50000, 100000, 250000)


def haversine_m(lat1, lon1, lat2, lon2, R) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    """Rumbo inicial de 1 a 2, en grados (0 = norte, 90 = este), como el Heading del juego."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def turn_deg(bearing: float, heading: float) -> float:
    """Giro de -180 (izquierda) a +180 (derecha)."""
    return (bearing - heading + 540) % 360 - 180


def nice_scale(d: float, minimum: float = 250) -> float:
    for s in SCALES_M:
        if s >= max(d * 1.15, minimum):
            return s
    return SCALES_M[-1]


def usable(s: dict) -> bool:
    return not s.get("depleted") and not s.get("notWorth")


def fmt_dist(m: float) -> str:
    if m < 1000:
        return f"{int(round(m / 10.0) * 10)} m"
    return f"{m / 1000:.1f} km".replace(".", ",")


def turn_text(t: float) -> str:
    a = abs(t)
    if a < 8:
        return "de frente ↑"
    if a > 165:
        return "detrás de ti ↓"
    return f"gira {int(round(a))}° a la {'derecha ↗' if t > 0 else 'izquierda ↖'}"


def site_label(s: dict) -> str:
    rigs = s.get("rigs")
    txt = str(s.get("mineral") or s.get("type") or "?")
    if s.get("depleted"):
        return txt + " (agotado)"
    if s.get("notWorth"):
        return txt + " · no rentable"
    if rigs:
        txt += f" ×{int(rigs)}"
    return txt


def build_view(st: dict, sites: list, target_id: Optional[str] = None, in_srv: bool = True) -> Optional[dict]:
    """De la posición (lat, lon, heading, radius) y los sitios saca todo lo que dibuja el overlay."""
    if not st or not st.get("has_ll") or not st.get("radius") or st.get("lat") is None:
        return None
    lat, lon, R = st["lat"], st["lon"], st["radius"]
    heading = st.get("heading") or 0.0
    items = []
    for s in sites:
        if s.get("lat") is None or s.get("lon") is None:
            continue
        d = haversine_m(lat, lon, s["lat"], s["lon"], R)
        b = bearing_deg(lat, lon, s["lat"], s["lon"])
        items.append(dict(s, dist=d, bearing=b, rel=turn_deg(b, heading), label=site_label(s)))
    items.sort(key=lambda x: x["dist"])
    target = None
    if target_id:
        target = next((x for x in items if str(x.get("id")) == str(target_id)), None)
    if target is None:
        target = next((x for x in items if usable(x)), None)
    nxt = next((x for x in items if usable(x) and x is not target), None)
    # La escala cubre el objetivo; sin objetivo, el sitio más cercano. En la nave, mínimo 2 km.
    ref = target["dist"] if target else (items[0]["dist"] if items else 0)
    scale = nice_scale(ref, 250 if in_srv else 2000)
    return {"heading": heading, "scale": scale, "items": items, "target": target, "next": nxt}


class BodySites:
    """Sitios de la flota del cuerpo actual, descargados de la hoja en segundo plano."""

    def __init__(self, logger: logging.Logger, get_url: Callable[[], str], get_token: Callable[[], str],
                 get_cmdr: Callable[[], str], http_get: Optional[Callable] = None):
        self.log = logger
        self.get_url, self.get_token, self.get_cmdr = get_url, get_token, get_cmdr
        self.http_get = http_get or (requests.get if requests else None)
        self.key = None            # (sistema, cuerpo) de los sitios cargados
        self.sites: list = []
        self.local: list = []      # marcados ahora mismo, aún no descargados
        self.fetched_at = 0.0
        self.next_try = 0.0
        self.busy = False
        self.status = ""

    def want(self, system: Optional[str], body: Optional[str], force: bool = False) -> None:
        if not system or not body:
            return
        key = (system, body)
        now = time.time()
        if key != self.key:
            self.key, self.sites, self.local, self.fetched_at, self.next_try = key, [], [], 0.0, 0.0
        due = force or (self.fetched_at == 0 and now >= self.next_try) or now - self.fetched_at > REFRESH_S
        if due and not self.busy and now >= self.next_try:
            self.busy = True
            threading.Thread(target=self.fetch, args=(key,), name="SkullMiningSites", daemon=True).start()

    def all(self) -> list:
        known = {(round(s.get("lat", 0), 5), round(s.get("lon", 0), 5), s.get("type")) for s in self.sites}
        extra = [s for s in self.local if (round(s["lat"], 5), round(s["lon"], 5), s.get("type")) not in known]
        return self.sites + extra

    def add_local(self, system: str, body: str, site: dict) -> None:
        if self.key == (system, body):
            self.local.append(site)
            self.next_try = time.time() + 20   # dar tiempo a la hoja y volver a pedir
            self.fetched_at = 0.0

    def fetch(self, key) -> None:
        try:
            url, token, cmdr = self.get_url().strip(), self.get_token().strip(), self.get_cmdr().strip()
            if not url or not token or not cmdr or self.http_get is None:
                self.status = "Mapa: falta la URL, la clave o el CMDR"
                self.next_try = time.time() + RETRY_S
                return
            r = self.http_get(url, timeout=30, params={"view": "body", "system": key[0], "body": key[1],
                                                       "cmdr": cmdr, "key": token})
            data = r.json() if r.status_code == 200 else {}
            if not data.get("ok"):
                err = data.get("error") or r.status_code
                self.status = {"auth": "Mapa: clave incorrecta", "member": "Mapa: tu CMDR no está en la lista de la flota"} \
                    .get(err, f"Mapa: la hoja respondió {err}")
                self.log.info(f"Sitios del cuerpo: {self.status}")
                self.next_try = time.time() + RETRY_S
                return
            if self.key == key:
                self.sites = data.get("sites") or []
                self.fetched_at = time.time()
                self.status = ""
                self.log.info(f"Mapa: {len(self.sites)} sitios de la flota en {key[1]}")
        except Exception as e:
            self.status = "Mapa: sin conexión con la hoja"
            self.log.info(f"Sitios del cuerpo: {e}")
            self.next_try = time.time() + RETRY_S
        finally:
            self.busy = False
