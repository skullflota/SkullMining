"""
Skull Mining - seguimiento de sesiones de minería en superficie.

No depende de EDMC: recibe eventos del journal y lecturas del Status.json
y produce "registros" (dicts) listos para enviar a la hoja de la flota.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import skull_analysis as analysis

PLUGIN_VERSION = "0.3.1"

# Bits de Flags / Flags2 del Status.json
FLAG_HAS_LATLONG = 1 << 21
FLAG_IN_MAINSHIP = 1 << 24
FLAG_IN_FIGHTER = 1 << 25
FLAG_IN_SRV = 1 << 26
FLAG_ALT_FROM_AVG_RADIUS = 1 << 29
FLAG2_ON_FOOT = 1 << 0

# Muestreo del recorrido
MIN_POINT_INTERVAL_S = 1.0
MIN_POINT_MOVE_M = 3.0
# Cerrar sesión si no hay posición en la superficie durante este tiempo
SESSION_IDLE_CLOSE_S = 15 * 60
# Guardado de la sesión en curso (para no perderla si EDMC se cierra y para poder revisarla)
LIVE_SAVE_EVERY_S = 20.0

# Eventos que ya tratamos explícitamente
KNOWN_EVENTS = {
    "MiningRefined", "LaunchSRV", "DockSRV", "SRVDestroyed", "Scan", "SAASignalsFound",
    "FSDJump", "Location", "CarrierJump", "Touchdown", "Liftoff", "MarketSell",
    "Shutdown", "ApproachBody", "LeaveBody", "Embark", "Disembark",
    "MaterialCollected", "CargoTransfer", "Cargo", "SupercruiseExit", "ModuleInfo",
}
SITE_SIGNAL_RE = re.compile(r"PlanetaryMiningLocation_Name;:#index=(\d+)", re.I)


def site_signal_index(text: Optional[str]) -> Optional[int]:
    """'$SAA_Unknown_Signal:#type=$PlanetaryMiningLocation_Name;:#index=3;' -> 3"""
    if not text:
        return None
    m = SITE_SIGNAL_RE.search(text)
    return int(m.group(1)) if m else None
# Palabras que delatan eventos nuevos del Rhino que aún no conocemos
DISCOVERY_KEYWORDS = ("mining", "rig", "deposit", "refin", "rhino", "extract", "srv", "prospect", "harvest")

# Mercancías de superficie (nombre interno probable). Sirve para registrar ventas
# aunque EDMC se haya reiniciado después de minar.
KNOWN_SURFACE_TYPES = {
    "monazite", "alexandrite", "grandidierite", "iridium", "periclasedunite", "thortveitite",
    "serendibite", "rhodplumsite", "diamond", "lowtemperaturediamond", "sapphire", "ruby",
    "helium", "helium3", "bastnasite", "platinum", "osmium", "tritium", "palladium", "gold",
    "quartzpyroxenite", "jadeite", "deuterium", "magnesite", "silver", "olivine", "samarium",
    "tantalum", "thorium", "uranium", "titanium", "uraninite", "methanolmonohydratecrystals",
    "hematite", "lithium", "copper", "water",
}


def parse_ts(ts: Optional[str]) -> float:
    if not ts:
        return time.time()
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return time.time()


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_type(raw: Optional[str]) -> str:
    """'$monazite_name;' -> 'monazite'"""
    if not raw:
        return "desconocido"
    s = raw.strip().lower()
    if s.startswith("$"):
        s = s[1:]
    if s.endswith(";"):
        s = s[:-1]
    if s.endswith("_name"):
        s = s[:-5]
    return s


class SurfaceSession:
    def __init__(self, system: dict, body: str, radius: float, t: float, srv_type: Optional[str]):
        self.id = str(uuid.uuid4())
        self.system = dict(system)
        self.body = body
        self.planet_radius = radius
        self.start_t = t
        self.end_t = t
        self.srv_type = srv_type
        self.track: List[tuple] = []
        self.refined: List[dict] = []
        self.events: List[dict] = []
        self.materials: Dict[str, int] = {}
        self.loads: List[int] = []
        self.site_signal: Optional[int] = None
        self.alt_avg_votes = [0, 0]  # [no, sí]

    def add_point(self, t: float, lat: float, lon: float, alt: Optional[float], alt_from_avg: bool) -> None:
        self.alt_avg_votes[1 if alt_from_avg else 0] += 1
        if self.track:
            lt, llat, llon, _ = self.track[-1]
            if t - lt < MIN_POINT_INTERVAL_S:
                return
            if analysis.haversine_m(llat, llon, lat, lon, self.planet_radius) < MIN_POINT_MOVE_M and t - lt < 10:
                return
        self.track.append((t, lat, lon, alt))
        self.end_t = max(self.end_t, t)

    def to_state(self) -> dict:
        return {k: getattr(self, k) for k in (
            "id", "system", "body", "planet_radius", "start_t", "end_t", "srv_type", "track", "refined",
            "events", "materials", "loads", "site_signal", "alt_avg_votes")}

    @classmethod
    def from_state(cls, st: dict) -> "SurfaceSession":
        obj = cls(st.get("system") or {}, st["body"], st.get("planet_radius") or 0.0, st["start_t"], st.get("srv_type"))
        for k, v in st.items():
            if k == "track":
                v = [tuple(p) for p in v]
            setattr(obj, k, v)
        return obj

    def to_dict(self) -> dict:
        return {
            "planet_radius": self.planet_radius,
            "track": self.track,
            "refined": self.refined,
            "alt_from_avg_radius": self.alt_avg_votes[1] > self.alt_avg_votes[0],
            "start_t": self.start_t,
        }


class Tracker:
    def __init__(self, emit: Callable[[str, dict], None], live_path: Optional[str] = None):
        """emit(kind, data) se llama con cada registro listo para enviar.

        live_path: archivo donde se guarda la sesión en curso cada pocos segundos.
        Si al arrancar existe y es reciente, la sesión se retoma.
        """
        self.emit = emit
        self.live_path = live_path
        self.last_live_save = 0.0
        self.cmdr: Optional[str] = None
        self.system: dict = {}
        self.bodies: Dict[str, dict] = {}
        self.body_signals: Dict[str, list] = {}
        self.status: dict = {}
        self.session: Optional[SurfaceSession] = None
        self.srv_type: Optional[str] = None
        self.mined_types: set = set()
        self.last_surface_t: float = 0.0
        self.last_site_signal: Optional[dict] = None
        self._restore_live()

    # -------------------------------------------------------------- persistencia
    def _restore_live(self) -> None:
        if not self.live_path or not os.path.exists(self.live_path):
            return
        try:
            with open(self.live_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            sess = SurfaceSession.from_state(st["session"])
            if time.time() - sess.end_t < SESSION_IDLE_CLOSE_S:
                self.session = sess
                self.cmdr = st.get("cmdr")
                self.system = st.get("system") or sess.system
                self.last_surface_t = sess.end_t
            else:
                # sesión vieja que no se cerró bien: se envía tal cual
                self.session = sess
                self.cmdr = st.get("cmdr")
                self.close_session("recuperada al arrancar")
        except Exception:
            pass

    def save_live(self, force: bool = False) -> None:
        if not self.live_path or not self.session:
            return
        now = time.time()
        if not force and now - self.last_live_save < LIVE_SAVE_EVERY_S:
            return
        self.last_live_save = now
        st = {"cmdr": self.cmdr, "system": self.system, "saved_at": now,
              "session": self.session.to_state(), "summary": analysis.summarize(self.session.to_dict())}
        tmp = self.live_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(st, f)
            os.replace(tmp, self.live_path)
        except OSError:
            pass

    def _drop_live(self) -> None:
        if self.live_path and os.path.exists(self.live_path):
            try:
                os.remove(self.live_path)
            except OSError:
                pass

    def set_context(self, cmdr: Optional[str], system: Optional[str], state: Optional[dict]) -> None:
        """Contexto de EDMC: sirve cuando EDMC se abre con el juego ya en marcha."""
        if cmdr:
            self.cmdr = cmdr
        if system and not self.system.get("name"):
            self.system = {"name": system,
                           "address": (state or {}).get("SystemAddress"),
                           "pos": (state or {}).get("StarPos")}
        if self.session and not self.session.system.get("name") and self.system.get("name"):
            self.session.system = dict(self.system)

    # ------------------------------------------------------------------ status
    def on_status(self, entry: dict) -> None:
        flags = entry.get("Flags", 0) or 0
        flags2 = entry.get("Flags2", 0) or 0
        t = parse_ts(entry.get("timestamp"))
        if not (flags & FLAG_HAS_LATLONG) or "Latitude" not in entry:
            self.status = {"t": t, "has_ll": False}
            self._check_idle(t)
            return
        self.status = {
            "t": t,
            "has_ll": True,
            "lat": entry.get("Latitude"),
            "lon": entry.get("Longitude"),
            "alt": entry.get("Altitude"),
            "body": entry.get("BodyName"),
            "radius": entry.get("PlanetRadius"),
            "in_srv": bool(flags & FLAG_IN_SRV),
            "on_foot": bool(flags2 & FLAG2_ON_FOOT),
            "alt_avg": bool(flags & FLAG_ALT_FROM_AVG_RADIUS),
        }
        s = self.status
        dest = entry.get("Destination") or {}
        idx = site_signal_index(dest.get("Name"))
        if idx is not None and s["body"]:
            self.last_site_signal = {"body": s["body"], "index": idx}
            if self.session and self.session.body == s["body"] and self.session.site_signal is None:
                self.session.site_signal = idx
        on_surface = s["in_srv"] or s["on_foot"]
        if not on_surface:
            self._check_idle(t)
            return
        self.last_surface_t = t
        if self.session and s["body"] and s["body"] != self.session.body:
            self.close_session("cambio de cuerpo")
        if self.session is None and s["in_srv"]:
            self._open_session(t)
        if self.session:
            if not self.session.planet_radius and s["radius"]:
                self.session.planet_radius = s["radius"]
            self.session.add_point(t, s["lat"], s["lon"], s["alt"], s["alt_avg"])
            self.save_live()

    def _check_idle(self, t: float) -> None:
        if self.session and self.last_surface_t and t - self.last_surface_t > SESSION_IDLE_CLOSE_S:
            self.close_session("inactividad")

    # ----------------------------------------------------------------- journal
    def on_journal(self, cmdr: Optional[str], entry: dict) -> None:
        if cmdr:
            self.cmdr = cmdr
        ev = entry.get("event", "")
        t = parse_ts(entry.get("timestamp"))

        if ev in ("FSDJump", "Location", "CarrierJump"):
            if self.session:
                if ev == "Location":
                    # Location llega al entrar en el juego: al salir, las plataformas se destruyen
                    self.close_session("salida del juego")
                elif entry.get("StarSystem") != self.system.get("name"):
                    self.close_session("salto")
            self.system = {
                "name": entry.get("StarSystem"),
                "address": entry.get("SystemAddress"),
                "pos": entry.get("StarPos"),
            }
        elif ev == "Scan" and entry.get("BodyName"):
            info = {
                "body": entry.get("BodyName"),
                "body_id": entry.get("BodyID"),
                "planet_class": entry.get("PlanetClass"),
                "gravity_g": round((entry.get("SurfaceGravity") or 0) / 9.80665, 3),
                "temp_k": entry.get("SurfaceTemperature"),
                "radius_m": entry.get("Radius"),
                "landable": entry.get("Landable"),
                "atmosphere": entry.get("Atmosphere") or entry.get("AtmosphereType"),
                "volcanism": entry.get("Volcanism"),
                "dist_ls": entry.get("DistanceFromArrivalLS"),
            }
            self.bodies[info["body"]] = info
        elif ev == "SAASignalsFound" and entry.get("BodyName"):
            sigs = entry.get("Signals", [])
            self.body_signals[entry["BodyName"]] = sigs
            info = self.bodies.setdefault(entry["BodyName"], {"body": entry["BodyName"]})
            info["body_id"] = entry.get("BodyID")
            for sg in sigs:
                if "planetarymininglocation" in str(sg.get("Type", "")).lower():
                    info["mining_locations"] = sg.get("Count")
            self.emit("body", self._body_record(entry["BodyName"], t))
        elif ev == "LaunchSRV":
            self.srv_type = entry.get("SRVType") or entry.get("SRVType_Localised")  # p. ej. "mev_rhino"
            if self.session is None and self.status.get("has_ll"):
                self._open_session(t)
            elif self.session is not None:
                self.session.srv_type = self.srv_type
        elif ev in ("DockSRV", "SRVDestroyed"):
            if self.session:
                self.session.events.append({"t": t, "event": ev})
            self.close_session(ev)
        elif ev == "Touchdown":
            idx = site_signal_index(entry.get("NearestDestination"))
            if idx is not None and entry.get("Body"):
                self.last_site_signal = {"body": entry["Body"], "index": idx}
        elif ev == "MaterialCollected" and self.session:
            name = entry.get("Name_Localised") or entry.get("Name") or "?"
            self.session.materials[name] = self.session.materials.get(name, 0) + (entry.get("Count") or 1)
        elif ev == "CargoTransfer" and self.session:
            n = sum(t.get("Count", 0) for t in entry.get("Transfers", []) if t.get("Direction") == "toship")
            if n:
                self.session.loads.append(n)
        elif ev in ("Liftoff", "LeaveBody", "Shutdown"):
            if self.session and ev != "Liftoff":
                self.close_session(ev)
        elif ev == "MiningRefined":
            typ = clean_type(entry.get("Type"))
            self.mined_types.add(typ)
            s = self.status
            if self.session is None and s.get("has_ll") and (s.get("in_srv") or s.get("on_foot")):
                self._open_session(t)
            if self.session:
                self.session.refined.append({
                    "t": t,
                    "type": typ,
                    "name": entry.get("Type_Localised") or typ,
                    "lat": s.get("lat") if s.get("has_ll") else None,
                    "lon": s.get("lon") if s.get("has_ll") else None,
                })
                self.session.end_t = max(self.session.end_t, t)
                self.save_live(force=True)
        elif ev == "MarketSell":
            typ = clean_type(entry.get("Type"))
            if typ in self.mined_types or typ in KNOWN_SURFACE_TYPES:
                self.emit("sale", {
                    "time": iso(t),
                    "cmdr": self.cmdr,
                    "type": typ,
                    "name": entry.get("Type_Localised") or typ,
                    "count": entry.get("Count"),
                    "sell_price": entry.get("SellPrice"),
                    "total": entry.get("TotalSale"),
                    "market_id": entry.get("MarketID"),
                    "system": self.system.get("name"),
                })

        if ev not in KNOWN_EVENTS and any(k in ev.lower() for k in DISCOVERY_KEYWORDS):
            rec = {"time": iso(t), "cmdr": self.cmdr, "event": ev, "raw": entry,
                   "system": self.system.get("name"), "body": self.status.get("body"),
                   "lat": self.status.get("lat"), "lon": self.status.get("lon")}
            if self.session:
                self.session.events.append({"t": t, "event": ev, "raw": entry})
            self.emit("event", rec)

    # ---------------------------------------------------------------- sessions
    def _open_session(self, t: float) -> None:
        s = self.status
        self.session = SurfaceSession(self.system, s.get("body") or "?", s.get("radius") or 0.0, t, self.srv_type)
        ls = self.last_site_signal
        if ls and ls["body"] == self.session.body:
            self.session.site_signal = ls["index"]
        self.last_surface_t = t

    def _body_record(self, body: str, t: float) -> dict:
        info = dict(self.bodies.get(body, {"body": body}))
        info.update({
            "time": iso(t),
            "system": self.system.get("name"),
            "system_address": self.system.get("address"),
            "signals": self.body_signals.get(body, []),
            "cmdr": self.cmdr,
        })
        return info

    def close_session(self, reason: str = "") -> Optional[dict]:
        sess, self.session = self.session, None
        self._drop_live()
        if sess is None:
            return None
        if not sess.refined:
            return None  # sin minería: no se envía nada (privacidad)
        summary = analysis.summarize(sess.to_dict())
        body = self.bodies.get(sess.body, {})
        track = analysis.downsample(sess.track)
        rec = {
            "session_id": sess.id,
            "plugin_version": PLUGIN_VERSION,
            "cmdr": self.cmdr,
            "system": sess.system.get("name"),
            "system_address": sess.system.get("address"),
            "star_pos": sess.system.get("pos"),
            "body": sess.body,
            "planet_class": body.get("planet_class"),
            "gravity_g": body.get("gravity_g"),
            "temp_k": body.get("temp_k"),
            "atmosphere": body.get("atmosphere"),
            "planet_radius_m": sess.planet_radius,
            "srv_type": sess.srv_type,
            "site_signal": sess.site_signal,
            "mining_locations_on_body": body.get("mining_locations"),
            "materials": sess.materials,
            "loads_to_ship": sess.loads,
            "start": iso(sess.start_t),
            "end": iso(sess.end_t),
            "close_reason": reason,
            "alt_from_avg_radius": sess.to_dict()["alt_from_avg_radius"],
            "summary": summary,
            "unknown_events": [e["event"] for e in sess.events if e.get("raw")],
            "track": analysis.encode_track(track, sess.start_t) if track else "",
        }
        self.emit("session", rec)
        return rec

    def live_text(self) -> str:
        if not self.session:
            return "Esperando sesión en superficie"
        n = len(self.session.refined)
        return f"Grabando en {self.session.body} · {n} t refinadas · {len(self.session.track)} puntos"
