"""
Skull Mining - plugin de EDMC para la flota Skull.

Registra sesiones de minería en superficie con el Rhino (plataformas,
distancias, orografía, toneladas) y las envía a la hoja compartida de la flota.
"""
from __future__ import annotations

import logging
import os
import sys
import tkinter as tk
from typing import Optional

import myNotebook as nb  # type: ignore  (lo proporciona EDMC)
from config import appname, config  # type: ignore

PLUGIN_NAME = os.path.basename(os.path.dirname(__file__))
logger = logging.getLogger(f"{appname}.{PLUGIN_NAME}")

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import skull_tracker  # noqa: E402
import skull_uploader  # noqa: E402

CFG_URL = "skullmining_url"
CFG_TOKEN = "skullmining_token"
CFG_ALIAS = "skullmining_alias"
CFG_ENABLED = "skullmining_enabled"


class _State:
    tracker: Optional[skull_tracker.Tracker] = None
    uploader: Optional[skull_uploader.Uploader] = None
    label: Optional[tk.Label] = None
    net_status: str = ""
    url_var: Optional[tk.StringVar] = None
    token_var: Optional[tk.StringVar] = None
    alias_var: Optional[tk.StringVar] = None
    enabled_var: Optional[tk.IntVar] = None


S = _State()


def _cfg(key: str, default: str = "") -> str:
    try:
        return config.get_str(key, default=default) or default
    except Exception:
        return default


def _enabled() -> bool:
    try:
        return bool(config.get_int(CFG_ENABLED, default=1))
    except Exception:
        return True


def _emit(kind: str, data: dict) -> None:
    if not _enabled() or S.uploader is None:
        return
    alias = _cfg(CFG_ALIAS).strip()
    if alias and "cmdr" in data:
        data["cmdr"] = alias
    S.uploader.send(kind, data)


def _set_net_status(text: str) -> None:
    S.net_status = text  # se pinta desde el hilo principal en _refresh_label


# ----------------------------------------------------------------- EDMC hooks
def plugin_start3(plugin_dir: str) -> str:
    S.uploader = skull_uploader.Uploader(
        plugin_dir, logger,
        get_url=lambda: _cfg(CFG_URL),
        get_token=lambda: _cfg(CFG_TOKEN),
        on_status=_set_net_status,
    )
    S.uploader.start()
    S.tracker = skull_tracker.Tracker(_emit, live_path=os.path.join(plugin_dir, "live_session.json"))
    logger.info(f"Skull Mining {skull_tracker.PLUGIN_VERSION} iniciado")
    return "Skull Mining"


def plugin_stop() -> None:
    if S.tracker:
        # No se cierra la sesión: queda guardada y se retoma al volver a abrir EDMC
        S.tracker.save_live(force=True)
    if S.uploader:
        S.uploader.stop()


def plugin_app(parent: tk.Frame):
    frame = tk.Frame(parent)
    tk.Label(frame, text="Skull Mining:").grid(row=0, column=0, sticky=tk.W)
    S.label = tk.Label(frame, text="Iniciando…", anchor=tk.W, justify=tk.LEFT)
    S.label.grid(row=0, column=1, sticky=tk.EW)
    frame.columnconfigure(1, weight=1)
    frame.after(2000, _refresh_label, frame)
    return frame


def _refresh_label(frame: tk.Frame) -> None:
    if S.label is not None and S.tracker is not None:
        txt = S.tracker.live_text()
        if not _enabled():
            txt = "Desactivado"
        elif not _cfg(CFG_URL) or not _cfg(CFG_TOKEN):
            txt = "Configura la URL y la clave en Ajustes"
        elif S.uploader and S.uploader.pending_count():
            txt += f" · {S.uploader.pending_count()} pendientes"
        S.label["text"] = txt
    frame.after(2000, _refresh_label, frame)


def plugin_prefs(parent, cmdr: str, is_beta: bool):
    f = nb.Frame(parent)
    S.enabled_var = tk.IntVar(value=1 if _enabled() else 0)
    S.url_var = tk.StringVar(value=_cfg(CFG_URL))
    S.token_var = tk.StringVar(value=_cfg(CFG_TOKEN))
    S.alias_var = tk.StringVar(value=_cfg(CFG_ALIAS))

    nb.Checkbutton(f, text="Enviar mis sesiones de minería en superficie a la flota Skull",
                   variable=S.enabled_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(10, 4))
    nb.Label(f, text="URL de la flota").grid(row=1, column=0, sticky=tk.W, padx=10)
    nb.Entry(f, textvariable=S.url_var, width=70).grid(row=1, column=1, sticky=tk.EW, padx=10)
    nb.Label(f, text="Clave de la flota").grid(row=2, column=0, sticky=tk.W, padx=10)
    nb.Entry(f, textvariable=S.token_var, width=30, show="•").grid(row=2, column=1, sticky=tk.W, padx=10)
    nb.Label(f, text="Alias (opcional)").grid(row=3, column=0, sticky=tk.W, padx=10)
    nb.Entry(f, textvariable=S.alias_var, width=30).grid(row=3, column=1, sticky=tk.W, padx=10)
    nb.Label(f, text=("Solo se envían sesiones en superficie en las que has refinado algo, y ventas de "
                      "minerales. Si pones un alias, se usa en lugar de tu nombre de comandante."),
             wraplength=500, justify=tk.LEFT).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=10, pady=8)
    nb.Label(f, text=f"Versión {skull_tracker.PLUGIN_VERSION}").grid(row=5, column=0, sticky=tk.W, padx=10)
    return f


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    if S.url_var is not None:
        config.set(CFG_URL, S.url_var.get().strip())
        config.set(CFG_TOKEN, S.token_var.get().strip())
        config.set(CFG_ALIAS, S.alias_var.get().strip())
        config.set(CFG_ENABLED, int(S.enabled_var.get()))


def journal_entry(cmdr, is_beta, system, station, entry, state):
    if is_beta or S.tracker is None:
        return None
    try:
        S.tracker.set_context(cmdr, system, state)
        S.tracker.on_journal(cmdr, entry)
    except Exception:
        logger.exception("Error procesando evento del journal")
    return None


def dashboard_entry(cmdr, is_beta, entry):
    if is_beta or S.tracker is None:
        return None
    try:
        S.tracker.on_status(entry)
    except Exception:
        logger.exception("Error procesando Status.json")
    return None
