"""
Skull Mining - plugin de EDMC para la flota Skull.

Registra sesiones de minería en superficie con el Rhino (taladros,
distancias, orografía, toneladas) y las envía a la hoja compartida de la flota.
"""
from __future__ import annotations

import logging
import os
import re
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
import skull_sites  # noqa: E402
import skull_overlay  # noqa: E402

CFG_URL = "skullmining_url"
CFG_TOKEN = "skullmining_token"
CFG_ALIAS = "skullmining_alias"
CFG_ENABLED = "skullmining_enabled"
CFG_OV = "skullmining_overlay"           # minimapa encima del juego (v0.9.0)
CFG_OV_X = "skullmining_overlay_x"
CFG_OV_Y = "skullmining_overlay_y"
CFG_OV_SIZE = "skullmining_overlay_size"
CFG_OV_ALPHA = "skullmining_overlay_alpha"
CFG_OV_BORDER = "skullmining_overlay_border"
CFG_OV_DIST = "skullmining_overlay_dist"
HIDE_GUI = {5, 6, 7, 8, 9, 10, 11}       # servicios, mapas, FSS, sondas, códice: el minimapa estorba


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
    sites = None
    overlay = None
    ov_var = None
    target_var = None
    target_menu = None
    target_ids: dict = {}
    target_keys: tuple = ()
    ov_cfg = (None, None, 300, 0.85, None, None)
    ov_error_logged = False


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
    S.sites = skull_sites.BodySites(logger, get_url=lambda: _cfg(CFG_URL), get_token=lambda: _cfg(CFG_TOKEN),
                                    get_cmdr=_current_cmdr)
    _load_ov_cfg()
    return "Skull Mining"


def plugin_stop() -> None:
    if S.tracker:
        # No se cierra la sesión: queda guardada y se retoma al volver a abrir EDMC
        S.tracker.save_live(force=True)
    if S.uploader:
        S.uploader.stop()
    if S.overlay is not None:
        try:
            S.overlay.close()
        except Exception:
            pass


def plugin_app(parent: tk.Frame):
    frame = tk.Frame(parent)
    tk.Label(frame, text="Skull Mining:").grid(row=0, column=0, sticky=tk.W)
    S.label = tk.Label(frame, text="Iniciando…", anchor=tk.W, justify=tk.LEFT)
    S.label.grid(row=0, column=1, sticky=tk.EW)
    frame.columnconfigure(1, weight=1)
    _build_form(frame)
    S.overlay = skull_overlay.Overlay(frame)
    frame.after(2000, _refresh_label, frame)
    frame.after(1000, _overlay_tick, frame)
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
        _style_menu(om)
        om.grid(row=i, column=1, sticky=tk.EW, padx=(6, 0), pady=1)

    btns = tk.Frame(f)
    btns.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(3, 0))
    tk.Button(btns, text="Enviar a web Skullmining", command=_send_form).pack(side=tk.LEFT)
    tk.Button(btns, text="Ir a web Skullmining", command=_open_web).pack(side=tk.LEFT, padx=(6, 0))
    # Minimapa encima del juego y objetivo al que guiar
    ovr = tk.Frame(f)
    ovr.grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(3, 0))
    S.ov_var = tk.IntVar(value=_cfg_int(CFG_OV, 0))
    tk.Checkbutton(ovr, text="Mapa en el juego", variable=S.ov_var,
                   command=lambda: config.set(CFG_OV, int(S.ov_var.get()))).pack(side=tk.LEFT)
    tk.Label(ovr, text="Ir a").pack(side=tk.LEFT, padx=(8, 2))
    S.target_var = tk.StringVar(value=AUTO_TARGET)
    S.target_menu = tk.OptionMenu(ovr, S.target_var, AUTO_TARGET)
    _style_menu(S.target_menu)
    S.target_menu.configure(width=190)   # en píxeles, al llevar imagen
    S.target_menu.pack(side=tk.LEFT)
    # Botón de actualización: solo aparece cuando hay una versión nueva en GitHub
    S.upd_btn = tk.Button(btns, text="", command=_on_update)
    S.upd_shown = None


AUTO_TARGET = "Elegir sitio en zona"   # sin elegir nada, el mapa guía al sitio rentable más cercano


def _circle_image() -> tk.PhotoImage:
    """Circulito gris que sustituye al rectángulo de los desplegables de Tk."""
    if getattr(S, "circle_img", None) is None:
        n, c, r = 12, 5.5, 4.6
        img = tk.PhotoImage(width=n, height=n)
        for y in range(n):
            for x in range(n):
                d = ((x - c) ** 2 + (y - c) ** 2) ** 0.5
                if abs(d - r) < 0.75:
                    img.put("#7a7a7a", (x, y))
        S.circle_img = img
    return S.circle_img


def _style_menu(om: tk.OptionMenu) -> None:
    """Desplegable sin el rectángulo de la derecha, con un círculo en su lugar."""
    try:
        om.configure(indicatoron=False, image=_circle_image(), compound=tk.RIGHT, anchor=tk.W,
                     highlightthickness=0, padx=6)
    except tk.TclError:
        om.configure(anchor=tk.W, highlightthickness=0)


def _cfg_int(key: str, default: int) -> int:
    try:
        v = config.get_int(key, default=default)
        return default if v is None else int(v)
    except Exception:
        return default


def _load_ov_cfg() -> None:
    def num(key):
        v = _cfg(key).strip()
        try:
            return int(v) if v else None
        except ValueError:
            return None
    size = num(CFG_OV_SIZE) or 300
    alpha = num(CFG_OV_ALPHA) or 85
    color = lambda key: _cfg(key).strip() if re.match(r"^#[0-9a-fA-F]{6}$", _cfg(key).strip()) else None
    S.ov_cfg = (num(CFG_OV_X), num(CFG_OV_Y), size, alpha / 100.0, color(CFG_OV_BORDER), color(CFG_OV_DIST))


def _update_targets(view_items: list) -> None:
    """Rellena el desplegable "Ir a" con los sitios del planeta (los rentables primero)."""
    if S.target_menu is None:
        return
    items = sorted(view_items, key=lambda x: (not skull_sites.usable(x), x["dist"]))[:25]
    ids = {}
    for x in items:
        # Sin distancia: el menú no se rehace al moverte y se quedaría vieja (la buena está en el mapa)
        name = x["label"] + (f" · zona {x['zone']}" if x.get("zone") not in (None, "") else "")
        while name in ids:
            name += " "
        ids[name] = str(x.get("id"))
    keys = tuple(sorted(str(x.get("id")) for x in items))
    if keys == S.target_keys:
        return                     # mismos sitios: no se reconstruye el menú (las distancias se ven en el mapa)
    S.target_keys, S.target_ids = keys, ids
    menu = S.target_menu["menu"]
    menu.delete(0, "end")
    for label in [AUTO_TARGET] + list(ids):
        menu.add_command(label=label, command=lambda v=label: S.target_var.set(v))
    if S.target_var.get() not in ids:
        S.target_var.set(AUTO_TARGET)


def _overlay_tick(frame: tk.Frame) -> None:
    try:
        on = bool(S.ov_var.get()) if S.ov_var is not None else False
        st = S.tracker.status if S.tracker is not None else {}
        if not on or S.overlay is None or not st.get("has_ll") or (st.get("gui") or 0) in HIDE_GUI:
            if S.overlay is not None:
                S.overlay.hide()
        else:
            system, body = S.tracker.system.get("name"), st.get("body")
            S.sites.want(system, body)
            sites = S.sites.all() if S.sites.key == (system, body) else []
            target_id = S.target_ids.get(S.target_var.get()) if S.target_var is not None else None
            view = skull_sites.build_view(st, sites, target_id, in_srv=bool(st.get("in_srv") or st.get("on_foot")))
            if view:
                _update_targets(view["items"])
            S.overlay.configure(*S.ov_cfg)
            S.overlay.draw(view, S.sites.status)
    except Exception:
        if not S.ov_error_logged:
            logger.exception("Error en el minimapa")
            S.ov_error_logged = True
    frame.after(500, _overlay_tick, frame)


def _pick_color(var: tk.StringVar, swatch: tk.Label, parent) -> None:
    try:
        from tkinter import colorchooser
        _rgb, hexcol = colorchooser.askcolor(color=var.get(), parent=parent, title="Elige un color")
    except Exception:
        return
    if hexcol:
        var.set(hexcol)
        swatch.configure(bg=hexcol)


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
            st, tr = S.tracker.status, S.tracker
            typ = by_name.get(S.min_var.get())
            if S.sites is not None and st.get("lat") is not None:
                S.sites.add_local(tr.system.get("name"), st.get("body"), {
                    "id": f"nuevo-{int(time.time())}", "type": typ, "mineral": S.min_var.get(), "lat": st["lat"],
                    "lon": st["lon"], "rigs": 1 if S.one_var.get() else (rigs or None), "zone": zone})
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
    x, y, size, alpha, border, dist = S.ov_cfg
    S.ovborder_var = tk.StringVar(value=border or skull_overlay.ORANGE)
    S.ovdist_var = tk.StringVar(value=dist or skull_overlay.WHITE)
    S.ovx_var = tk.StringVar(value="" if x is None else str(x))
    S.ovy_var = tk.StringVar(value="" if y is None else str(y))
    S.ovsize_var = tk.StringVar(value=str(size))
    S.ovalpha_var = tk.StringVar(value=str(int(round(alpha * 100))))
    nb.Label(f, text="Mapa en el juego (necesita el juego en «ventana sin bordes»)").grid(
        row=5, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(10, 2))
    g = nb.Frame(f)
    g.grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=10)
    for i, (lbl, var, w) in enumerate((("Posición X", S.ovx_var, 6), ("Y", S.ovy_var, 6),
                                       ("Tamaño (px)", S.ovsize_var, 5), ("Opacidad (%)", S.ovalpha_var, 4))):
        nb.Label(g, text=lbl).grid(row=0, column=2 * i, sticky=tk.W, padx=(0 if i == 0 else 10, 4))
        _entry(g, textvariable=var, width=w).grid(row=0, column=2 * i + 1, sticky=tk.W)
    c = nb.Frame(f)
    c.grid(row=9, column=0, columnspan=2, sticky=tk.W, padx=10, pady=(4, 0))
    for i, (lbl, var) in enumerate((("Color del borde", S.ovborder_var), ("Color de las distancias", S.ovdist_var))):
        nb.Label(c, text=lbl).grid(row=0, column=3 * i, sticky=tk.W, padx=(0 if i == 0 else 16, 4))
        sw = tk.Label(c, text="      ", bg=var.get(), relief=tk.SOLID, bd=1)
        sw.grid(row=0, column=3 * i + 1)
        tk.Button(c, text="Elegir…", command=lambda v=var, w=sw: _pick_color(v, w, c)).grid(row=0, column=3 * i + 2, padx=(4, 0))
    nb.Label(f, text="Deja X e Y vacíos para ponerlo arriba a la derecha. Se activa con la casilla «Mapa en el juego» "
                     "de la ventana de EDMC.", wraplength=500, justify=tk.LEFT).grid(row=7, column=0, columnspan=2,
                                                                                    sticky=tk.W, padx=10, pady=(2, 8))
    nb.Label(f, text=f"Versión {skull_tracker.PLUGIN_VERSION}").grid(row=10, column=0, sticky=tk.W, padx=10, pady=(8, 0))
    return f


def prefs_changed(cmdr: str, is_beta: bool) -> None:
    if S.url_var is not None:
        config.set(CFG_URL, S.url_var.get().strip())
        config.set(CFG_TOKEN, S.token_var.get().strip())
        config.set(CFG_ALIAS, S.alias_var.get().strip())
        config.set(CFG_ENABLED, int(S.enabled_var.get()))
        if getattr(S, "ovx_var", None) is not None:
            for key, var in ((CFG_OV_X, S.ovx_var), (CFG_OV_Y, S.ovy_var), (CFG_OV_SIZE, S.ovsize_var),
                             (CFG_OV_ALPHA, S.ovalpha_var)):
                v = var.get().strip()
                config.set(key, v if v.lstrip("-").isdigit() else "")
            config.set(CFG_OV_BORDER, S.ovborder_var.get())
            config.set(CFG_OV_DIST, S.ovdist_var.get())
            _load_ov_cfg()
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
