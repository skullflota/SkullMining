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

PLUGIN_VERSION = "0.5.3"

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
# Radio máximo de una zona alrededor de su punto de bajada. Las zonas de planetas grandes son
# "gigantescas" (un minero cuenta conducir 4 km hasta un hotspot); se asigna siempre la más cercana.
ZONE_RADIUS_M = 10000.0
# Estados que el jugador puede marcar a mano para un sitio
# Lo que muestra el escáner del Rhino: "Density" (fija) y "Mineral amount" (lo que queda; baja al minar).
SITE_STATES = ("alto", "medio", "bajo", "cant_alta", "cant_media", "cant_baja", "agotado")
STATE_TEXT = {"alto": "Densidad alta", "medio": "Densidad media", "bajo": "Densidad baja",
              "cant_alta": "Cantidad alta", "cant_media": "Cantidad media", "cant_baja": "Cantidad baja",
              "agotado": "Agotado"}

# Eventos que ya tratamos explícitamente
KNOWN_EVENTS = {
    "MiningRefined", "LaunchSRV", "DockSRV", "SRVDestroyed", "Scan", "SAASignalsFound",
    "FSDJump", "Location", "CarrierJump", "Touchdown", "Liftoff", "MarketSell",
    "Shutdown", "ApproachBody", "LeaveBody", "Embark", "Disembark",
    "MaterialCollected", "CargoTransfer", "Cargo", "SupercruiseExit", "ModuleInfo", "EjectCargo",
}
SITE_SIGNAL_RE = re.compile(r"PlanetaryMiningLocation_Name;:#index=(\d+)", re.I)


def site_signal_index(text: Optional[str]) -> Optional[int]:
    """'$SAA_Unknown_Signal:#type=$PlanetaryMiningLocation_Name;:#index=3;' -> 3"""
    if not text:
        return None
    m = SITE_SIGNAL_RE.search(text)
    return int(m.group(1)) if m else None
# Palabras que delatan eventos nuevos del Rhino que aún no conocemos
DISCOVERY_KEYWORDS = ("mining", "rig", "deposit", "refin", "rhino", "extract", "srv", "prospect",
                      "harvest", "planetary", "chunk", "deplet", "density", "remaining", "surface")
# Campos conocidos de los eventos que usamos. Si Frontier añade otros (p. ej. el depósito o su
# desgaste en MiningRefined), se envían a la hoja para aprovecharlos cuanto antes.
KNOWN_FIELDS = {
    "MiningRefined": {"timestamp", "event", "Type", "Type_Localised"},
    "Touchdown": {"timestamp", "event", "PlayerControlled", "Taxi", "Multicrew", "StarSystem", "SystemAddress",
                  "Body", "BodyID", "OnStation", "OnPlanet", "Latitude", "Longitude", "NearestDestination",
                  "NearestDestination_Localised"},
    "LaunchSRV": {"timestamp", "event", "SRVType", "SRVType_Localised", "Loadout", "ID", "PlayerControlled"},
    "DockSRV": {"timestamp", "event", "SRVType", "SRVType_Localised", "ID"},
    "SAASignalsFound": {"timestamp", "event", "BodyName", "SystemAddress", "BodyID", "Signals", "Genuses"},
    "CargoTransfer": {"timestamp", "event", "Transfers"},
    "Status": {"timestamp", "event", "Flags", "Flags2", "Pips", "FireGroup", "GuiFocus", "Fuel", "Cargo",
               "LegalState", "Latitude", "Longitude", "Heading", "Altitude", "BodyName", "PlanetRadius",
               "Balance", "Destination", "Oxygen", "Health", "Temperature", "SelectedWeapon",
               "SelectedWeapon_Localised", "Gravity"},
    "Status.Destination": {"System", "Body", "Name", "Name_Localised"},
}
# Máximo de avisos por evento nuevo en cada arranque de EDMC (por si el evento se repite mucho)
DISCOVERY_MAX_PER_RUN = 5

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
        self.zone_anchors: Dict[str, list] = {}  # "3" -> [lat, lon, t, fuente]
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
            "events", "materials", "loads", "site_signal", "zone_anchors", "alt_avg_votes")}

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
    def __init__(self, emit: Callable[[str, dict], None], live_path: Optional[str] = None,
                 state_path: Optional[str] = None):
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
        # Zonas: la última zona fijada como destino se recuerda aunque se quite o se reinicie EDMC
        self.state_path = state_path
        self.body_names: Dict[str, str] = {}   # "sistema:bodyid" -> nombre del cuerpo
        self.zone_target: Optional[dict] = None
        self.zone_anchors: Dict[str, list] = {}  # "cuerpo|3" -> [lat, lon, t, fuente]
        self.discovered: Dict[str, int] = {}     # avisos de novedades enviados en este arranque
        self._restore_state()
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

    def _restore_state(self) -> None:
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            self.body_names = st.get("body_names", {})
            self.zone_target = st.get("zone_target")
            self.zone_anchors = st.get("zone_anchors", {})
        except Exception:
            pass

    def _save_state(self) -> None:
        if not self.state_path:
            return
        # limitar tamaño: solo las últimas 200 anclas y 500 cuerpos
        if len(self.zone_anchors) > 200:
            keep = sorted(self.zone_anchors.items(), key=lambda kv: kv[1][2])[-200:]
            self.zone_anchors = dict(keep)
        if len(self.body_names) > 500:
            self.body_names = dict(list(self.body_names.items())[-500:])
        tmp = self.state_path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"body_names": self.body_names, "zone_target": self.zone_target,
                           "zone_anchors": self.zone_anchors}, f)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    # ------------------------------------------------------------------- zonas
    def _remember_body(self, system_address, body_id, name) -> None:
        if system_address is None or body_id is None or not name:
            return
        key = f"{system_address}:{body_id}"
        if self.body_names.get(key) != name:
            self.body_names[key] = name
            if self.zone_target and self.zone_target.get("body_id") == body_id \
                    and self.zone_target.get("system") == system_address and not self.zone_target.get("body"):
                self.zone_target["body"] = name
            self._save_state()

    def _set_zone_target(self, body: Optional[str], index: int, t: float, system_address=None,
                         body_id=None, on_surface: bool = False) -> None:
        zt = self.zone_target or {}
        if zt.get("index") == index and (zt.get("body") == body or (body_id is not None and zt.get("body_id") == body_id)):
            if body and not zt.get("body"):
                zt["body"] = body
                self._save_state()
            return
        self.zone_target = {"body": body, "index": index, "t": t, "system": system_address,
                            "body_id": body_id, "set_on_surface": on_surface}
        self._save_state()

    def _anchor_zone(self, body: str, index: int, lat: float, lon: float, t: float, source: str) -> None:
        key = f"{body}|{index}"
        if key in self.zone_anchors:
            return
        self.zone_anchors[key] = [lat, lon, t, source]
        if self.session and self.session.body == body:
            self.session.zone_anchors.setdefault(str(index), [lat, lon, t, source])
        self._save_state()

    def zone_at(self, body: Optional[str], lat: Optional[float], lon: Optional[float], radius_m: float) -> Optional[int]:
        """Zona de una posición: la ancla conocida más cercana dentro del radio de zona."""
        if not body or lat is None or lon is None or not radius_m:
            return None
        best, best_d = None, None
        for key, a in self.zone_anchors.items():
            b, _, idx = key.rpartition("|")
            if b != body:
                continue
            d = analysis.haversine_m(lat, lon, a[0], a[1], radius_m)
            if d <= ZONE_RADIUS_M and (best_d is None or d < best_d):
                best, best_d = int(idx), d
        if best is not None:
            return best
        zt = self.zone_target
        # Sin ancla cercana: la zona fijada como destino, si es de este cuerpo y no tiene ancla en otro sitio
        if zt and zt.get("body") == body and f"{body}|{zt['index']}" not in self.zone_anchors:
            return zt["index"]
        return None

    def current_zone(self) -> Optional[int]:
        s = self.status
        if not s.get("has_ll"):
            return None
        return self.zone_at(s.get("body"), s.get("lat"), s.get("lon"), s.get("radius") or 0)

    def mark_state(self, state: str) -> str:
        """El jugador marca el estado del sitio donde está (alto, medio, bajo, agotado)."""
        state = state.lower()
        if state not in SITE_STATES:
            return "Marca no válida"
        s = self.status
        if not s.get("has_ll") or not (s.get("in_srv") or s.get("on_foot")):
            return "Para marcar el estado tienes que estar en la superficie"
        lat, lon, body = s["lat"], s["lon"], s.get("body")
        mineral = None
        session_tonnes = 0
        if self.session and self.session.body == body and self.session.planet_radius:
            counts: Dict[str, int] = {}
            for r in self.session.refined:
                if r.get("lat") is None:
                    continue
                if analysis.haversine_m(lat, lon, r["lat"], r["lon"], self.session.planet_radius) <= analysis.SITE_LINK_M:
                    counts[r["type"]] = counts.get(r["type"], 0) + 1
            if counts:
                mineral = max(counts, key=counts.get)
                session_tonnes = counts[mineral]
        t = s.get("t") or time.time()
        rec = {"time": iso(t), "cmdr": self.cmdr, "system": self.system.get("name"), "body": body,
               "zone": self.current_zone(), "lat": lat, "lon": lon, "state": state, "type": mineral,
               "planet_radius_m": s.get("radius"),
               # toneladas de este mineral sacadas aquí en la sesión en curso (aún no enviada a la hoja)
               "session_tonnes": session_tonnes}
        if self.session:
            self.session.events.append({"t": t, "event": "EstadoSitio", "state": state, "lat": lat, "lon": lon})
        self.emit("state", rec)
        return STATE_TEXT[state] + " enviado" + (f" ({mineral}, {session_tonnes} t hoy)" if mineral else "")

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
        self._check_fields("Status", entry)
        if isinstance(entry.get("Destination"), dict):
            self._check_fields("Status.Destination", entry["Destination"], entry)
        flags = entry.get("Flags", 0) or 0
        flags2 = entry.get("Flags2", 0) or 0
        t = parse_ts(entry.get("timestamp"))
        if not (flags & FLAG_HAS_LATLONG) or "Latitude" not in entry:
            self._handle_destination(entry, t, None, False)
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
        on_surface = s["in_srv"] or s["on_foot"] or bool(flags & (1 << 1))  # bit 1 = aterrizado
        self._handle_destination(entry, t, s.get("body"), on_surface)
        zt = self.zone_target
        # Ancla de zona: primer punto en superficie tras fijar la zona desde el aire
        if on_surface and zt and not zt.get("set_on_surface") and zt.get("body") == s["body"]:
            self._anchor_zone(s["body"], zt["index"], s["lat"], s["lon"], t, "destino")
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

    def _handle_destination(self, entry: dict, t: float, body_here: Optional[str], on_surface: bool) -> None:
        dest = entry.get("Destination") or {}
        idx = site_signal_index(dest.get("Name"))
        if idx is None:
            return
        body_name = self.body_names.get(f"{dest.get('System')}:{dest.get('Body')}")
        if body_name is None and body_here:
            body_name = body_here  # fijada estando ya junto a ese cuerpo
        self._set_zone_target(body_name, idx, t, dest.get("System"), dest.get("Body"), on_surface)
        if body_name:
            self.last_site_signal = {"body": body_name, "index": idx}
            if self.session and self.session.body == body_name and self.session.site_signal is None:
                self.session.site_signal = idx

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
                    # Location llega al entrar en el juego: al salir, los taladros se destruyen
                    self.close_session("salida del juego")
                elif entry.get("StarSystem") != self.system.get("name"):
                    self.close_session("salto")
            self.system = {
                "name": entry.get("StarSystem"),
                "address": entry.get("SystemAddress"),
                "pos": entry.get("StarPos"),
            }
        if ev in ("ApproachBody", "Touchdown", "Liftoff", "SupercruiseExit", "LeaveBody", "Location"):
            self._remember_body(entry.get("SystemAddress"), entry.get("BodyID"), entry.get("Body"))
        elif ev in ("SAASignalsFound", "Scan"):
            self._remember_body(entry.get("SystemAddress"), entry.get("BodyID"), entry.get("BodyName"))

        if ev == "Scan" and entry.get("BodyName"):
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
                self._set_zone_target(entry["Body"], idx, t, entry.get("SystemAddress"), entry.get("BodyID"), False)
                if entry.get("Latitude") is not None:
                    self._anchor_zone(entry["Body"], idx, entry["Latitude"], entry["Longitude"], t, "aterrizaje")
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
                    "zone": self.current_zone(),
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

        if ev not in KNOWN_EVENTS and not ev.startswith("Colonisation") \
                and any(k in ev.lower() for k in DISCOVERY_KEYWORDS):
            self._report_discovery(ev, entry, t)
        elif ev in KNOWN_FIELDS:
            self._check_fields(ev, entry)

    # ----------------------------------------------------------- novedades del juego
    def _check_fields(self, name: str, obj: dict, raw: Optional[dict] = None) -> None:
        new = sorted(k for k in obj if k not in KNOWN_FIELDS.get(name, ()))
        if new:
            self._report_discovery(f"CamposNuevos:{name}:" + ",".join(new), raw or obj,
                                   parse_ts((raw or obj).get("timestamp")))

    def _report_discovery(self, ev: str, entry: dict, t: float) -> None:
        n = self.discovered.get(ev, 0)
        if n >= DISCOVERY_MAX_PER_RUN:
            return
        self.discovered[ev] = n + 1
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
        for key, a in self.zone_anchors.items():
            b, _, idx = key.rpartition("|")
            if b == self.session.body:
                self.session.zone_anchors[idx] = a
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
        self._assign_site_zones(sess, summary)
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
            "zones": [{"index": int(k), "lat": v[0], "lon": v[1], "source": v[3]} for k, v in sess.zone_anchors.items()],
            "mining_locations_on_body": body.get("mining_locations"),
            "materials": sess.materials,
            "loads_to_ship": sess.loads,
            "start": iso(sess.start_t),
            "end": iso(sess.end_t),
            "close_reason": reason,
            "alt_from_avg_radius": sess.to_dict()["alt_from_avg_radius"],
            "summary": summary,
            "unknown_events": sorted({e["event"] for e in sess.events if e.get("raw")}),
            "track": analysis.encode_track(track, sess.start_t) if track else "",
            # Cada tonelada con su hora, posición y zona: permite recalcular la sesión más adelante
            "refined_raw": analysis.encode_refined(sess.refined, sess.start_t),
            "session_start_t": sess.start_t,
            "zone_known": any(r.get("zone") is not None for r in sess.refined),
        }
        self.emit("session", rec)
        return rec

    def _assign_site_zones(self, sess: SurfaceSession, summary: dict) -> None:
        """Zona de cada sitio: la más repetida entre sus refinados; si no hay, la ancla más cercana."""
        R = sess.planet_radius
        for site in summary.get("sites", []) or []:
            votes: Dict[int, int] = {}
            for r in sess.refined:
                if r.get("zone") is None or r.get("lat") is None or r["type"] != site["main_type"]:
                    continue
                if analysis.haversine_m(site["lat"], site["lon"], r["lat"], r["lon"], R) <= analysis.SITE_LINK_M:
                    votes[r["zone"]] = votes.get(r["zone"], 0) + 1
            if votes:
                site["zone"] = max(votes, key=votes.get)
            else:
                site["zone"] = self.zone_at(sess.body, site["lat"], site["lon"], R)

    def zone_missing(self) -> bool:
        """En el SRV grabando, pero sin saber en qué zona estamos."""
        return bool(self.session) and self.status.get("has_ll", False) and self.current_zone() is None

    def live_text(self) -> str:
        if not self.session:
            return "Esperando sesión en superficie"
        n = len(self.session.refined)
        z = self.current_zone()
        if z is None:
            return (f"Grabando en {self.session.body} · {n} t refinadas\n"
                    "⚠ Zona desconocida: fija la zona como destino (mapa del planeta o panel izquierdo)")
        return f"Grabando en {self.session.body} · zona {z} · {n} t refinadas"
