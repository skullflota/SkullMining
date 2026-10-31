"""v0.9.0: minimapa (cálculo de la vista y descarga de sitios del cuerpo)."""
import logging, math, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "SkullMining"))
import skull_sites as S

R = 1500000.0
m = lambda meters: meters / (R * math.pi / 180)


def test_geometria():
    assert abs(S.bearing_deg(0, 0, 1, 0) - 0) < 0.01 and abs(S.bearing_deg(0, 0, 0, 1) - 90) < 0.01
    assert abs(S.turn_deg(10, 350) - 20) < 1e-9 and abs(S.turn_deg(350, 10) + 20) < 1e-9
    assert S.nice_scale(420) == 500 and S.nice_scale(100) == 250 and S.nice_scale(100, 2000) == 2000
    assert S.turn_text(3) == "de frente ↑" and "derecha" in S.turn_text(40) and "izquierda" in S.turn_text(-40)
    assert S.fmt_dist(412) == "410 m" and S.fmt_dist(2500) == "2,5 km"


def test_vista():
    st = {"has_ll": True, "lat": 0.0, "lon": 0.0, "radius": R, "heading": 90.0}
    sites = [{"id": "near-bad", "type": "iridium", "lat": 0, "lon": m(100), "rigs": 1, "notWorth": True},
             {"id": "dep", "type": "osmium", "lat": m(150), "lon": 0, "rigs": 2, "depleted": "x"},
             {"id": "good", "type": "iridium", "lat": 0, "lon": m(400), "rigs": 3},
             {"id": "far", "type": "monazite", "lat": m(3000), "lon": 0, "rigs": 4},
             {"id": "nopos", "type": "gold"}]
    v = S.build_view(st, sites)
    assert v["target"]["id"] == "good"                    # el rentable más cercano
    assert abs(v["target"]["rel"]) < 0.5                  # al este, y miro al este: de frente
    assert v["next"]["id"] == "far" and v["scale"] == 500 and len(v["items"]) == 4
    v2 = S.build_view(st, sites, target_id="far")
    assert v2["target"]["id"] == "far" and v2["scale"] == 5000 and abs(v2["target"]["rel"] + 90) < 0.5
    assert S.build_view({"has_ll": False}, sites) is None
    assert S.build_view(st, [])["target"] is None


class R_:
    def __init__(self, js, code=200): self._js, self.status_code = js, code
    def json(self): return self._js


def test_descarga():
    calls = []
    def get(url, timeout, params):
        calls.append(params)
        return R_({"ok": True, "sites": [{"id": "S1", "type": "iridium", "lat": 1, "lon": 2}]}) if params["key"] == "k" \
            else R_({"ok": False, "error": "auth"})
    b = S.BodySites(logging.getLogger("t"), lambda: "https://x/exec", lambda: "k", lambda: "Yo", http_get=get)
    b.want("Sis", "B1")
    for _ in range(50):
        if not b.busy: break
        time.sleep(0.02)
    assert [s["id"] for s in b.all()] == ["S1"] and calls[0]["view"] == "body" and calls[0]["cmdr"] == "Yo"
    b.add_local("Sis", "B1", {"id": "nuevo", "type": "platinum", "lat": 5.0, "lon": 6.0})
    assert [s["id"] for s in b.all()] == ["S1", "nuevo"]
    time.sleep(0.01)
    b.fetch(("Sis", "B1"))                                 # la hoja ya la tiene (unida al S1): no se ve dos veces
    assert [s["id"] for s in b.all()] == ["S1"]
    b.want("Sis", "B2")                                    # otro cuerpo: se vacía y se pide de nuevo
    for _ in range(50):
        if not b.busy: break
        time.sleep(0.02)
    assert calls[-1]["body"] == "B2"
    bad = S.BodySites(logging.getLogger("t"), lambda: "https://x/exec", lambda: "mal", lambda: "Yo", http_get=get)
    bad.fetch(("Sis", "B1")); assert "clave" in bad.status


def test_errores():
    class ConnectTimeout(Exception): pass
    class SSLError(Exception): pass
    class ConnectionError_(Exception): pass
    assert "no responde a tiempo" in S.explain_error(ConnectTimeout("Connection to script.google.com timed out"))
    assert "certificado" in S.explain_error(SSLError("certificate verify failed"))
    assert "no se puede conectar" in S.explain_error(ConnectionError_("getaddrinfo failed"))
    class Html:
        status_code, text = 200, "<!DOCTYPE html><html>Sign in</html>"
        def json(self): raise ValueError("Expecting value")
    b = S.BodySites(logging.getLogger("t"), lambda: "https://x/exec", lambda: "k", lambda: "Yo",
                    http_get=lambda *a, **k: Html())
    b.fetch(("Sis", "B1")); assert "no devuelve datos" in b.status, b.status
    def boom(*a, **k): raise ConnectTimeout("timed out")
    b2 = S.BodySites(logging.getLogger("t"), lambda: "https://x/exec", lambda: "k", lambda: "Yo", http_get=boom)
    b2.fetch(("Sis", "B1")); assert "no responde a tiempo" in b2.status
    old = S.BodySites(logging.getLogger("t"), lambda: "https://x/exec", lambda: "k", lambda: "Yo",
                      http_get=lambda *a, **k: R_({"ok": False, "error": "token"}))
    old.fetch(("Sis", "B1")); assert "antigua" in old.status


if __name__ == "__main__":
    test_geometria(); test_vista(); test_descarga(); test_errores(); print("OK test_mapa")
