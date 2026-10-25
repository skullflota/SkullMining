"""
Skull Mining - minimapa encima del juego (v0.9.0).

Ventana propia de Tk sin bordes, siempre encima, con un color transparente y que deja pasar los clics
al juego (Windows). Solo se ve con el juego en "ventana sin bordes"; en pantalla completa no hay forma
de pintar encima. El mapa va orientado según el rumbo: arriba es hacia donde miras.
"""
from __future__ import annotations

import math
import sys
import tkinter as tk
from typing import Optional

import skull_sites as sitesmod

KEY = "#010203"            # color que Windows vuelve transparente
ORANGE, YELLOW, WHITE, GREY = "#ff8a1f", "#ffd23f", "#f2f2f2", "#8c8c8c"
RED, AMBER, PANEL = "#ff5d5d", "#ffc857", "#14161c"
MINERAL_COLORS = ("#4fd1ff", "#b28dff", "#45d483", "#ff9de2", "#7cf0e0", "#9fb8ff", "#c7f08a", "#f0a3ff")   # sin amarillo: es el del objetivo


def mineral_color(s: dict) -> str:
    if s.get("depleted"):
        return GREY
    if s.get("notWorth"):
        return RED
    name = str(s.get("type") or s.get("mineral") or "")
    return MINERAL_COLORS[sum(map(ord, name)) % len(MINERAL_COLORS)]


def _click_through(win: tk.Toplevel) -> None:
    """Los clics pasan al juego y la ventana no roba el foco (solo Windows)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
        GWL_EXSTYLE = -20
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000   # LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    except Exception:
        pass


class Overlay:
    def __init__(self, root: tk.Misc):
        self.root = root
        self.win: Optional[tk.Toplevel] = None
        self.cv: Optional[tk.Canvas] = None
        self.size = 300
        self.pos = (None, None)
        self.alpha = 0.85
        self.border = ORANGE      # color del borde (círculo, recuadro, N)
        self.dist_color = WHITE   # color de las cifras de distancia
        self.visible = False

    def configure(self, x: Optional[int], y: Optional[int], size: int, alpha: float,
                  border: Optional[str] = None, dist_color: Optional[str] = None) -> None:
        self.border = border or ORANGE
        self.dist_color = dist_color or WHITE
        changed = (x, y) != self.pos or size != self.size or abs(alpha - self.alpha) > 0.001
        self.pos, self.size, self.alpha = (x, y), max(180, min(700, int(size))), max(0.3, min(1.0, alpha))
        if changed and self.win is not None:
            self._destroy()   # se vuelve a crear con la nueva geometría en el siguiente dibujo

    def _create(self) -> None:
        w, h = self.size, int(self.size * 1.32) + 4
        win = tk.Toplevel(self.root)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-transparentcolor", KEY)
        except tk.TclError:
            pass
        try:
            win.attributes("-alpha", self.alpha)
        except tk.TclError:
            pass
        x, y = self.pos
        if x is None or y is None:
            x, y = win.winfo_screenwidth() - w - 40, 120
        win.geometry(f"{w}x{h}+{int(x)}+{int(y)}")
        cv = tk.Canvas(win, width=w, height=h, bg=KEY, highlightthickness=0, bd=0)
        cv.pack(fill=tk.BOTH, expand=True)
        win.deiconify()
        win.update_idletasks()
        _click_through(win)
        self.win, self.cv = win, cv

    def _destroy(self) -> None:
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win, self.cv, self.visible = None, None, False

    def hide(self) -> None:
        if self.win is not None and self.visible:
            self.win.withdraw()
            self.visible = False

    def close(self) -> None:
        self._destroy()

    # ------------------------------------------------------------------ dibujo
    def draw(self, view: Optional[dict], note: str = "") -> None:
        if self.win is None:
            self._create()
        if not self.visible:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.visible = True
        cv, S = self.cv, self.size
        cv.delete("all")
        cx, cy, r = S / 2, S / 2, S / 2 - 6
        f_small = ("Segoe UI", max(8, int(S / 34)))
        f_norm = ("Segoe UI", max(9, int(S / 28)))
        f_bold = ("Segoe UI", max(10, int(S / 24)), "bold")
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, fill=PANEL, outline=self.border, width=2)
        if view is None:
            cv.create_text(cx, cy, text=note or "Acércate a un planeta", fill=WHITE, font=f_norm, width=S - 40)
            return
        scale, heading = view["scale"], view["heading"]
        cv.create_oval(cx - r / 2, cy - r / 2, cx + r / 2, cy + r / 2, outline=self.border, dash=(2, 6))
        cv.create_text(cx + 4, cy - r / 2 - 8, text=sitesmod.fmt_dist(scale / 2), fill=self.dist_color, font=f_small, anchor="w")
        # Norte en el borde (el mapa gira con el rumbo)
        a = math.radians(-heading)
        cv.create_text(cx + (r - 10) * math.sin(a), cy - (r - 10) * math.cos(a), text="N", fill=self.border, font=f_small)

        def at(item):
            k = min(item["dist"] / scale, 1.0) * (r - 8)
            ang = math.radians(item["rel"])
            return cx + k * math.sin(ang), cy - k * math.cos(ang), item["dist"] > scale

        target = view.get("target")
        if target:
            tx, ty, _ = at(target)
            cv.create_line(cx, cy, tx, ty, fill=YELLOW, width=2, dash=(6, 3))
        shown = 0
        for it in sorted(view["items"], key=lambda i: -i["dist"]):
            x, y, outside = at(it)
            col = mineral_color(it)
            rad = 4 if outside else 6
            cv.create_oval(x - rad, y - rad, x + rad, y + rad, fill="" if outside else col, outline=col, width=2)
            is_t = target is not None and it is target
            if is_t:
                cv.create_oval(x - 10, y - 10, x + 10, y + 10, outline=YELLOW, width=2)
            if (not outside and shown < 8) or is_t:
                gap = 14 if is_t else 9
                if x > S * 0.6:   # cerca del borde derecho: el texto a la izquierda del punto
                    cv.create_text(x - gap, y, text=it["label"], fill=col, font=f_small, anchor="e")
                else:
                    cv.create_text(x + gap, y, text=it["label"], fill=col, font=f_small, anchor="w")
                shown += 1
        # Tú, en el centro, mirando hacia arriba
        cv.create_polygon(cx, cy - 11, cx - 8, cy + 8, cx, cy + 3, cx + 8, cy + 8, fill=WHITE, outline="#000000")
        # Recuadro con el objetivo
        top = S + 6
        # El recuadro acaba 4 px antes del final de la ventana: así se ve el borde de abajo
        cv.create_rectangle(4, top, S - 4, top + S * 0.30, fill=PANEL, outline=self.border, width=2)
        if target:
            extra = f" · zona {target['zone']}" if target.get("zone") not in (None, "") else ""
            cv.create_text(12, top + 6, text="→ " + target["label"] + extra, fill=YELLOW, font=f_bold, anchor="nw",
                           width=S - 24)
            d_item = cv.create_text(12, top + 6 + S * 0.09, anchor="nw", fill=self.dist_color, font=f_bold,
                                    text=sitesmod.fmt_dist(target["dist"]))
            x2 = (cv.bbox(d_item) or (0, 0, 12 + S * 0.25, 0))[2]
            cv.create_text(x2 + 6, top + 6 + S * 0.09, anchor="nw", fill=WHITE, font=f_norm,
                           text="· " + sitesmod.turn_text(target["rel"]))
            nxt = view.get("next")
            if nxt:
                cv.create_text(12, top + 6 + S * 0.17, anchor="nw", fill=GREY, font=f_small,
                               text=f"Siguiente: {nxt['label']} a {sitesmod.fmt_dist(nxt['dist'])}")
        else:
            cv.create_text(12, top + 8, anchor="nw", fill=WHITE, font=f_norm, width=S - 24,
                           text=note or ("Sin sitios rentables conocidos en este planeta" if view["items"]
                                         else "La flota no tiene sitios en este planeta"))
