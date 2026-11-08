"""
Skull Mining - colocar taladros (v0.10.0).

El juego no apunta en ningún sitio dónde se coloca un taladro, así que el comandante lo indica:
mantener pulsado 1 s el clic de la rueda del ratón = "taladro colocado aquí"; doble clic = deshacer el último.
Aquí se guardan esos taladros y se calcula si la posición actual respeta la separación mínima (47 m).
Sin Tk ni Windows: se puede probar fuera de EDMC. La lectura del botón (Windows) está al final.
"""
from __future__ import annotations

import sys
import time
from typing import List, Optional

import skull_sites as sitesmod

MIN_SPACING_M = 47.0      # separación mínima entre taladros (medida en el juego)
HOLD_S = 1.0              # pulsación larga = marcar
DOUBLE_S = 0.45           # dos clics cortos en este tiempo = deshacer
SHORT_MAX_S = 0.35        # un "clic" corto dura menos que esto

# Botones del ratón que se pueden elegir (código virtual de Windows)
BUTTONS = {"Clic de la rueda": 0x04, "Botón lateral atrás": 0x05, "Botón lateral adelante": 0x06, "Desactivado": 0}
DEFAULT_BUTTON = "Clic de la rueda"


class PressDetector:
    """Convierte el estado del botón (pulsado o no, leído cada ~50 ms) en gestos: 'hold' o 'double'."""

    def __init__(self, hold_s: float = HOLD_S, double_s: float = DOUBLE_S, short_s: float = SHORT_MAX_S):
        self.hold_s, self.double_s, self.short_s = hold_s, double_s, short_s
        self.down_at: Optional[float] = None
        self.fired = False            # ya se dio el 'hold' de esta pulsación
        self.last_short_up: Optional[float] = None

    def update(self, pressed: bool, now: Optional[float] = None) -> Optional[str]:
        now = time.time() if now is None else now
        if pressed:
            if self.down_at is None:
                self.down_at, self.fired = now, False
            elif not self.fired and now - self.down_at >= self.hold_s:
                self.fired = True
                self.last_short_up = None
                return "hold"
            return None
        if self.down_at is None:
            return None
        dur, self.down_at = now - self.down_at, None
        if self.fired or dur > self.short_s:
            self.last_short_up = None
            return None
        if self.last_short_up is not None and now - self.last_short_up <= self.double_s:
            self.last_short_up = None
            return "double"
        self.last_short_up = now
        return None


class RigPlanner:
    """Taladros colocados en el planeta actual (se borran al cambiar de cuerpo o al subir el Rhino)."""

    def __init__(self):
        self.body: Optional[str] = None
        self.rigs: List[dict] = []
        self.flash: Optional[str] = None     # mensaje corto para el mapa ("Taladro 2 marcado")
        self.flash_until = 0.0

    def _say(self, text: str, secs: float = 2.5) -> None:
        self.flash, self.flash_until = text, time.time() + secs

    def message(self) -> Optional[str]:
        return self.flash if self.flash and time.time() < self.flash_until else None

    def set_body(self, body: Optional[str]) -> None:
        if body != self.body:
            self.body, self.rigs = body, []

    def add(self, lat: float, lon: float, body: Optional[str]) -> int:
        self.set_body(body)
        self.rigs.append({"lat": lat, "lon": lon, "t": time.time()})
        self._say(f"Taladro {len(self.rigs)} marcado")
        return len(self.rigs)

    def undo(self) -> bool:
        if not self.rigs:
            self._say("No hay taladros que borrar")
            return False
        self.rigs.pop()
        self._say(f"Taladro {len(self.rigs) + 1} borrado")
        return True

    def clear(self, say: bool = False) -> None:
        had = bool(self.rigs)
        self.rigs = []
        if say and had:
            self._say("Taladros borrados")

    def evaluate(self, lat: float, lon: float, heading: float, radius: float) -> dict:
        """Distancia y rumbo a cada taladro, y si aquí se puede colocar otro."""
        items, nearest = [], None
        for i, r in enumerate(self.rigs, start=1):
            d = sitesmod.haversine_m(lat, lon, r["lat"], r["lon"], radius)
            b = sitesmod.bearing_deg(lat, lon, r["lat"], r["lon"])
            it = {"n": i, "dist": d, "rel": sitesmod.turn_deg(b, heading)}
            items.append(it)
            if nearest is None or d < nearest["dist"]:
                nearest = it
        ok = nearest is None or nearest["dist"] >= MIN_SPACING_M
        missing = 0.0 if ok else MIN_SPACING_M - nearest["dist"]
        return {"rigs": items, "nearest": nearest, "ok": ok, "missing": missing, "count": len(items)}


def status_text(ev: dict) -> str:
    if not ev["count"]:
        return ""
    n = ev["nearest"]
    if ev["ok"]:
        return f"✔ Puedes colocar aquí · taladro {n['n']} a {sitesmod.fmt_dist(n['dist'])}"
    return f"✖ Aléjate {int(round(ev['missing']))} m del taladro {n['n']} (está a {int(round(n['dist']))} m)"


def button_pressed(vk: int) -> bool:
    """¿Está pulsado ahora este botón del ratón? (Windows; funciona con el juego en primer plano)."""
    if not vk or not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
    except Exception:
        return False
