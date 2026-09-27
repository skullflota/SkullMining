"""
Skull Mining - envío de registros a la hoja de la flota.

Cola en segundo plano con persistencia en disco: si no hay conexión o
Google falla, los registros se guardan en pending.json y se reintentan.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from typing import Callable, Optional

try:
    import requests
except ImportError:  # pragma: no cover - EDMC siempre incluye requests
    requests = None  # type: ignore

RETRY_MIN_S = 30
RETRY_MAX_S = 15 * 60


class Uploader:
    def __init__(self, plugin_dir: str, logger: logging.Logger,
                 get_url: Callable[[], str], get_token: Callable[[], str],
                 on_status: Optional[Callable[[str], None]] = None):
        self.path = os.path.join(plugin_dir, "pending.json")
        self.log = logger
        self.get_url = get_url
        self.get_token = get_token
        self.on_status = on_status or (lambda s: None)
        self.q: "queue.Queue[Optional[dict]]" = queue.Queue()
        self.lock = threading.Lock()
        self.pending = self._load()
        self.thread = threading.Thread(target=self._run, name="SkullMiningUploader", daemon=True)
        self.stop_flag = False

    def start(self) -> None:
        self.thread.start()
        if self.pending:
            self.q.put({"_kick": True})

    def stop(self) -> None:
        self.stop_flag = True
        self.q.put(None)
        self.thread.join(timeout=5)

    def send(self, kind: str, data: dict) -> None:
        item = {"kind": kind, "data": data, "queued_at": time.time()}
        with self.lock:
            self.pending.append(item)
            self._save()
        self.q.put({"_kick": True})

    def kick(self) -> None:
        """Reintentar ya (p. ej. tras cambiar la URL o la clave)."""
        self.q.put({"_kick": True, "_reset": True})

    def pending_count(self) -> int:
        with self.lock:
            return len(self.pending)

    # ------------------------------------------------------------------ interno
    def _load(self) -> list:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.pending, f)
            os.replace(tmp, self.path)
        except OSError as e:
            self.log.warning(f"No se pudo guardar la cola: {e}")

    def _post(self, item: dict) -> bool:
        url, token = self.get_url().strip(), self.get_token().strip()
        if not url or not token or requests is None:
            self.log.info("Sin URL o clave de la flota: no se envía")
            self.on_status("Falta configurar URL o clave de la flota")
            return False
        body = {"token": token, "kind": item["kind"], "data": item["data"]}
        try:
            r = requests.post(url, data=json.dumps(body), timeout=30,
                              headers={"Content-Type": "text/plain;charset=utf-8"})
            txt = r.text or ""
            if r.status_code == 200 and '"ok":true' in txt.replace(" ", ""):
                self.log.info(f"Enviado a la hoja: {item['kind']}")
                return True
            self.log.warning(f"Respuesta inesperada ({r.status_code}): {txt[:200]}")
            if '"error":"token"' in txt.replace(" ", ""):
                self.on_status("Clave de la flota incorrecta")
        except Exception as e:  # red, DNS, timeout...
            self.log.info(f"Envío fallido, se reintentará: {e}")
        return False

    def _run(self) -> None:
        delay = RETRY_MIN_S
        while not self.stop_flag:
            try:
                msg = self.q.get(timeout=delay)
            except queue.Empty:
                msg = {"_kick": True}
            if msg is None:
                break
            if msg.get("_reset"):
                delay = RETRY_MIN_S
            while not self.stop_flag:
                with self.lock:
                    if not self.pending:
                        break
                    item = self.pending[0]
                if self._post(item):
                    with self.lock:
                        if self.pending and self.pending[0] is item:
                            self.pending.pop(0)
                        self._save()
                    delay = RETRY_MIN_S
                    self.on_status(f"Enviado ({item['kind']}) · pendientes: {self.pending_count()}")
                else:
                    delay = min(delay * 2, RETRY_MAX_S)
                    self.on_status(f"Sin enviar · pendientes: {self.pending_count()}")
                    break
