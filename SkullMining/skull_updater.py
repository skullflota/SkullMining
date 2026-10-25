"""
Skull Mining - actualización del plugin desde las releases de GitHub.

Al arrancar EDMC se pregunta a GitHub cuál es la última release. Si es más nueva que la instalada,
el formulario muestra el botón amarillo "Actualizar plugin"; al pulsarlo se descarga el zip de la
release, se comprueba y se instalan sus ficheros encima de los actuales (los anteriores quedan en
la carpeta _anterior). Después hay que reiniciar EDMC.
"""
from __future__ import annotations

import io
import logging
import os
import re
import threading
import zipfile
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover - EDMC siempre incluye requests
    requests = None  # type: ignore

REPO = "skullflota/SkullMining"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ASSET_RE = re.compile(r"^SkullMining-v?\d+(\.\d+)*\.zip$", re.I)
ALLOWED_HOSTS = {"github.com", "api.github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com"}
INSTALL_EXT = (".py", ".md")          # solo código y el LEEME: nunca pending.json ni el estado guardado
MAX_ZIP_BYTES = 5 * 1024 * 1024

IDLE, AVAILABLE, DOWNLOADING, DONE, ERROR = "idle", "available", "downloading", "done", "error"


def parse_version(v: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(n) for n in nums[:4]) or (0,)


def _host_ok(url: str) -> bool:
    try:
        u = urlparse(url)
    except ValueError:
        return False
    return u.scheme == "https" and (u.hostname or "").lower() in ALLOWED_HOSTS


def latest_from_api(data: dict) -> Optional[dict]:
    """De la respuesta de GitHub saca {'version', 'url'} del zip del plugin (o None)."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    for a in data.get("assets") or []:
        name, url = str(a.get("name") or ""), str(a.get("browser_download_url") or "")
        if ASSET_RE.match(name) and _host_ok(url):
            return {"version": tag.lstrip("vV"), "url": url}
    return None


def install_zip(data: bytes, plugin_dir: str) -> list:
    """Instala los .py y .md del zip en plugin_dir. Comprueba todo antes de escribir nada."""
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError("zip demasiado grande")
    zf = zipfile.ZipFile(io.BytesIO(data))
    files = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        parts = info.filename.replace("\\", "/").split("/")
        if any(p in ("", ".", "..") for p in parts) or info.filename.startswith(("/", "\\")):
            raise ValueError(f"ruta no válida en el zip: {info.filename}")
        # el zip trae la carpeta SkullMining/...; se aceptan solo ficheros de primer nivel
        if len(parts) == 2:
            name = parts[1]
        elif len(parts) == 1:
            name = parts[0]
        else:
            continue  # subcarpetas (p. ej. __pycache__): se ignoran
        if not name.lower().endswith(INSTALL_EXT):
            continue
        files[name] = zf.read(info)
    if "load.py" not in files or "skull_tracker.py" not in files:
        raise ValueError("el zip no parece el plugin Skull Mining")
    for name, content in files.items():
        if name.endswith(".py"):
            compile(content, name, "exec")   # si no compila, no se instala nada
    backup = os.path.join(plugin_dir, "_anterior")
    os.makedirs(backup, exist_ok=True)
    for name, content in files.items():
        dest = os.path.join(plugin_dir, name)
        if os.path.exists(dest):
            with open(dest, "rb") as src, open(os.path.join(backup, name), "wb") as b:
                b.write(src.read())
        tmp = dest + ".tmp"
        with open(tmp, "wb") as f:
            f.write(content)
        os.replace(tmp, dest)
    return sorted(files)


class Updater:
    def __init__(self, plugin_dir: str, current: str, logger: logging.Logger,
                 http_get: Optional[Callable] = None):
        self.plugin_dir = plugin_dir
        self.current = current
        self.log = logger
        self.http_get = http_get or (requests.get if requests else None)
        self.state = IDLE
        self.latest: Optional[dict] = None
        self.error = ""

    # ----------------------------------------------------------- comprobar
    def check_async(self) -> None:
        threading.Thread(target=self.check, name="SkullMiningUpdateCheck", daemon=True).start()

    def check(self) -> None:
        if self.http_get is None:
            return
        try:
            r = self.http_get(API_LATEST, timeout=20, headers={"Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                self.log.info(f"Comprobar actualización: GitHub respondió {r.status_code}")
                return
            latest = latest_from_api(r.json())
            if latest and parse_version(latest["version"]) > parse_version(self.current):
                self.latest = latest
                self.state = AVAILABLE
                self.log.info(f"Hay una versión nueva del plugin: {latest['version']} (instalada {self.current})")
        except Exception as e:  # sin red, GitHub caído...: se vuelve a mirar al reiniciar EDMC
            self.log.info(f"No se pudo comprobar si hay actualización: {e}")

    # ----------------------------------------------------------- instalar
    def install_async(self) -> None:
        if self.state != AVAILABLE or not self.latest:
            return
        self.state = DOWNLOADING
        threading.Thread(target=self.install, name="SkullMiningUpdate", daemon=True).start()

    def install(self) -> None:
        try:
            url = self.latest["url"]
            r = self.http_get(url, timeout=60)
            if r.status_code != 200:
                raise ValueError(f"descarga fallida ({r.status_code})")
            if not _host_ok(getattr(r, "url", url) or url):
                raise ValueError("la descarga no viene de GitHub")
            names = install_zip(r.content, self.plugin_dir)
            self.state = DONE
            self.log.info(f"Plugin actualizado a {self.latest['version']}: {', '.join(names)}. Hay que reiniciar EDMC.")
        except Exception as e:
            self.error = str(e)
            self.state = ERROR
            self.log.warning(f"No se pudo actualizar el plugin: {e}")
