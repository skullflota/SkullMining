"""
Skull Mining - plugin de EDMC para la flota Skull.

Registra sesiones de minería en superficie con el Rhino (taladros,
distancias, orografía, toneladas) y las envía a la hoja compartida de la flota.
"""
from __future__ import annotations

import logging
import os
import sys
import time
import tkinter as tk
import urllib.parse
import webbrowser
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
import skull_updater  # noqa: E402

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
    updater = None
    upd_btn = None
    upd_shown = None


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
    S.tracker = skull_tracker.Tracker(_emit, live_path=os.path.join(plugin_dir, "live_session.json"),
                                      state_path=os.path.join(plugin_dir, "zone_state.json"))
    logger.info(f"Skull Mining {skull_tracker.PLUGIN_VERSION} iniciado")
    S.updater = skull_updater.Updater(plugin_dir, skull_tracker.PLUGIN_VERSION, logger)
    S.updater.check_async()
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
    _build_form(frame)
    frame.after(2000, _refresh_label, frame)
    return frame


# --------------------------------------------------------------- formulario
WEB_URL = "https://skullflota.github.io/SkullMining/"
NONE = "—"


def _build_form(frame: tk.Frame) -> None:
    """Formulario parecido al de RhinoSpotter: lo que dice el escáner del Rhino, enviado a la web de la flota."""
    f = tk.Frame(frame)
    f.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(3, 0))
    f.columnconfigure(1, weight=1)
    S.zone_var = tk.StringVar(value="")
    S.rigs_var = tk.StringVar(value="0")
    S.min_var = tk.StringVar(value=NONE)
    S.amount_var = tk.StringVar(value=NONE)
    S.density_var = tk.StringVar(value=NONE)
    S.one_var = tk.IntVar(value=0)
    S.touched = set()

    top = tk.Frame(f)
    top.grid(row=0, column=0, columnspan=2, sticky=tk.EW)
    tk.Label(top, text="Zona").pack(side=tk.LEFT)
    tk.Spinbox(top, from_=0, to=99, width=4, textvariable=S.zone_var,
               command=lambda: S.touched.add("zone")).pack(side=tk.LEFT, padx=(4, 12))
    tk.Label(top, text="Taladros").pack(side=tk.LEFT)
    tk.Spinbox(top, from_=0, to=7, width=3, textvariable=S.rigs_var,
               command=lambda: S.touched.add("rigs")).pack(side=tk.LEFT, padx=4)
    tk.Checkbutton(top, text="Solo cabe 1", variable=S.one_var, command=_one_rig_toggled).pack(side=tk.LEFT, padx=(8, 0))

    names = [NONE] + [es for _, es in skull_tracker.MINERALS]
    rows = (("Mineral", S.min_var, names, "mineral"),
            ("Cantidad", S.amount_var, [NONE] + list(skull_tracker.AMOUNTS), "amount"),
            ("Densidad", S.density_var, [NONE] + list(skull_tracker.DENSITIES), "density"))
    for i, (label, var, opts, key) in enumerate(rows, start=1):
        tk.Label(f, text=label).grid(row=i, column=0, sticky=tk.W)
        om = tk.OptionMenu(f, var, *opts, command=lambda _v, k=key: S.touched.add(k))
        om.configure(anchor=tk.W, highlightthickness=0)
        om.grid(row=i, column=1, sticky=tk.EW, padx=(6, 0), pady=1)

    btns = tk.Frame(f)
    btns.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(3, 0))
    tk.Button(btns, text="Enviar a web Skullmining", command=_send_form).pack(side=tk.LEFT)
    tk.Button(btns, text="Ir a web Skullmining", command=_open_web).pack(side=tk.LEFT, padx=(6, 0))
    # Botón de actualización: solo aparece cuando hay una versión nueva en GitHub
    S.upd_btn = tk.Button(btns, text="", command=_on_update)
    S.upd_shown = None


def _on_update() -> None:
    u = getattr(S, "updater", None)
    if u is None:
        return
    if u.state == skull_updater.AVAILABLE:
        u.install_async()
    elif u.state == skull_updater.ERROR:
        webbrowser.open(skull_updater.RELEASES_PAGE)   # que lo instale a mano
    _paint_update()


def _paint_update() -> None:
    """Pinta el botón según el estado de la actualización (desde el hilo de Tk, cada 2 s).
    Los colores se repiten siempre porque el tema de EDMC puede cambiarlos."""
    u, b = getattr(S, "updater", None), getattr(S, "upd_btn", None)
    if u is None or b is None:
        return
    state = u.state
    if state == skull_updater.IDLE:
        if S.upd_shown is not None:
            b.pack_forget()
            S.upd_shown = None
        return
    ver = (u.latest or {}).get("version", "")
    look = {
        skull_updater.AVAILABLE: (f"Actualizar plugin (v{ver})", tk.NORMAL, "#ffd23f"),
        skull_updater.DOWNLOADING: ("Actualizando…", tk.DISABLED, "#ffd23f"),
        skull_updater.DONE: ("Reinicia EDMC", tk.DISABLED, "#4ade80"),
    }.get(state, ("Error al actualizar: descárgalo a mano", tk.NORMAL, "#ff8f8f"))
    b.configure(text=look[0], state=look[1], bg=look[2], fg="#000000", disabledforeground="#000000",
                activebackground=look[2], activeforeground="#000000")
    if S.upd_shown is None:
        b.pack(side=tk.LEFT, padx=(6, 0))
    S.upd_shown = state


def _current_cmdr() -> str:
    """Nombre del comandante tal como sale en el juego (no el alias): es lo que se compara con la lista de la flota."""
    c = getattr(S.tracker, "cmdr", None) if S.tracker is not None else None
    if not c:
        try:
            from monitor import monitor  # type: ignore  (lo proporciona EDMC)
            c = monitor.cmdr
        except Exception:
            c = None
    if not c:
        try:
            cmdrs = config.get_list("cmdrs") or []
            c = cmdrs[-1] if cmdrs else None
        except Exception:
            c = None
    return str(c or "").strip()


def web_login_url(base: str, cmdr: str, key: str) -> str:
    """Enlace a la web que entra directamente. Los datos van detrás de '#': el navegador no los envía a GitHub
    y la web los borra de la barra de direcciones nada más leerlos."""
    if not cmdr or not key:
        return base
    return base + "#" + urllib.parse.urlencode({"cmdr": cmdr, "key": key}, quote_via=urllib.parse.quote)


def _open_web() -> None:
    cmdr, key = _current_cmdr(), _cfg(CFG_TOKEN).strip()
    if not key:
        _set_net_status("Web: falta la clave de la flota en Ajustes")
    elif not cmdr:
        _set_net_status("Web: abre el juego una vez para saber tu CMDR")
    webbrowser.open(web_login_url(WEB_URL, cmdr, key))


def _one_rig_toggled() -> None:
    """Marcar "Solo cabe 1" pone Taladros = 1 (no hace falta haber desplegado el taladro)."""
    if S.one_var.get():
        S.rigs_var.set("1")
        S.touched.add("rigs")


def _fill_form() -> None:
    """Rellena zona, mineral y taladros con lo que sabe el plugin, salvo lo que haya tocado el usuario."""
    if S.tracker is None or not hasattr(S, "zone_var"):
        return
    try:
        sug = S.tracker.suggest()
    except Exception:
        return
    if "zone" not in S.touched and sug.get("zone") is not None:
        S.zone_var.set(str(sug["zone"]))
    if "mineral" not in S.touched and sug.get("type"):
        S.min_var.set(dict(skull_tracker.MINERALS).get(sug["type"], S.min_var.get()))
    if "rigs" not in S.touched and sug.get("rigs"):
        S.rigs_var.set(str(sug["rigs"]))


def _send_form() -> None:
    if S.tracker is None:
        return
    by_name = {es: t for t, es in skull_tracker.MINERALS}
    get = lambda v: None if v.get() in ("", NONE) else v.get()
    try:
        zone = int(S.zone_var.get()) if S.zone_var.get().strip() else None
    except ValueError:
        zone = None
    try:
        rigs = int(S.rigs_var.get() or 0)
    except ValueError:
        rigs = 0
    try:
        msg = S.tracker.mark_site(zone, rigs, by_name.get(S.min_var.get()), get(S.amount_var), get(S.density_var),
                                  one_rig=bool(S.one_var.get()))
        if msg.startswith("Enviado"):
            S.touched.clear()       # el siguiente sitio vuelve a rellenarse solo
            S.amount_var.set(NONE)
            S.density_var.set(NONE)
            S.one_var.set(0)
    except Exception:
        logger.exception("Error enviando el sitio")
        msg = "No se pudo enviar el sitio"
    S.flash = msg
    S.flash_until = time.time() + 6
    if S.label is not None:
        S.label["text"] = msg


def _mark_state(state: str) -> None:
    if S.tracker is None:
        return
    try:
        msg = S.tracker.mark_state(state)
    except Exception:
        logger.exception("Error marcando el estado del sitio")
        msg = "No se pudo marcar el estado"
    S.flash = msg
    S.flash_until = time.time() + 6
    if S.label is not None:
        S.label["text"] = msg


def _refresh_label(frame: tk.Frame) -> None:
    try:
        _paint_update()
    except Exception:
        logger.exception("Botón de actualización")
    if S.label is not None and S.tracker is not None:
        _fill_form()
        txt = S.tracker.live_text()
        if not _enabled():
            txt = "Desactivado"
        elif not _cfg(CFG_URL) or not _cfg(CFG_TOKEN):
            txt = "Configura la URL y la clave en Ajustes"
        elif S.uploader and S.uploader.pending_count():
            txt += f" · {S.uploader.pending_count()} pendientes"
        warn = _enabled() and S.tracker.zone_missing()
        if time.time() < getattr(S, "flash_until", 0):
            txt = S.flash
        S.label["text"] = txt
        # Aviso en naranja; al quitarlo se recupera el color del tema de EDMC
        try:
            if warn and not getattr(S, "warned", False):
                S.saved_fg = S.label.cget("fg")
                S.label["fg"] = "#ff8a1f"
                S.warned = True
            elif not warn and getattr(S, "warned", False):
                S.label["fg"] = S.saved_fg
                S.warned = False
        except Exception:
            pass
    frame.after(2000, _refresh_label, frame)


def _entry(parent, **kw):
    """Campo de texto: EDMC moderno usa nb.EntryMenu; versiones viejas, nb.Entry."""
    cls = getattr(nb, "EntryMenu", None) or getattr(nb, "Entry", None) or tk.Entry
    return cls(parent, **kw)


def plugin_prefs(parent, cmdr: str, is_beta: bool):
    f = nb.Frame(parent)
    S.enabled_var = tk.IntVar(value=1 if _enabled() else 0)
    S.url_var = tk.StringVar(value=_cfg(CFG_URL))
    S.token_var = tk.StringVar(value=_cfg(CFG_TOKEN))
    S.alias_var = tk.StringVar(value=_cfg(CFG_ALIAS))

    nb.Checkbutton(f, text="Enviar mis sesiones de minería en superficie a la flota Skull",
                   variable=S.enabled_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(10, 4))
    nb.Label(f, text="URL de la flota").grid(row=1, column=0, sticky=tk.W, padx=10)
    _entry(f, textvariable=S.url_var, width=70).grid(row=1, column=1, sticky=tk.EW, padx=10)
    nb.Label(f, text="Clave de la flota").grid(row=2, column=0, sticky=tk.W, padx=10)
    _entry(f, textvariable=S.token_var, width=30, show="•").grid(row=2, column=1, sticky=tk.W, padx=10)
    nb.Label(f, text="Alias (opcional)").grid(row=3, column=0, sticky=tk.W, padx=10)
    _entry(f, textvariable=S.alias_var, width=30).grid(row=3, column=1, sticky=tk.W, padx=10)
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
        logger.info("Ajustes de Skull Mining guardados (URL %s, clave %s)",
                    "sí" if S.url_var.get().strip() else "no", "sí" if S.token_var.get().strip() else "no")
        if S.uploader:
            S.uploader.kick()


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
