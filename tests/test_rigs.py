"""v0.10.0: marcar taladros con el ratón y comprobar los 47 m."""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "SkullMining"))
import skull_rigs as G

R = 1500000.0
m = lambda x: x / (R * math.pi / 180)


def feed(det, pattern, t0=0.0, step=0.05):
    """pattern: lista de (pulsado, segundos)."""
    out, t = [], t0
    for pressed, secs in pattern:
        for _ in range(int(round(secs / step))):
            g = det.update(pressed, t)
            if g:
                out.append(g)
            t += step
    return out


def test_gestos():
    assert feed(G.PressDetector(), [(True, 1.3), (False, 0.5)]) == ["hold"]                 # mantener = marcar (una vez)
    assert feed(G.PressDetector(), [(True, 0.1), (False, 0.1), (True, 0.1), (False, 0.5)]) == ["double"]
    assert feed(G.PressDetector(), [(True, 0.1), (False, 1.0), (True, 0.1), (False, 1.0)]) == []   # clics sueltos
    assert feed(G.PressDetector(), [(True, 0.6), (False, 0.5)]) == []                        # ni corto ni largo
    assert feed(G.PressDetector(), [(True, 2.5), (False, 0.2)]) == ["hold"]                  # mantener mucho = 1 marca


def test_distancias():
    p = G.RigPlanner()
    assert p.min_m == 75
    p.min_m = 47
    p.add(0, 0, "B 1")
    ev = p.evaluate(0, m(30), 90, R)
    assert not ev["ok"] and round(ev["missing"]) == 17 and "Aléjate 17 m" in G.status_text(ev)
    ev = p.evaluate(0, m(50), 90, R)
    assert ev["ok"] and "Puedes colocar" in G.status_text(ev)
    assert abs(ev["nearest"]["rel"] - 180) < 1 or abs(ev["nearest"]["rel"] + 180) < 1   # el taladro queda detrás
    p.add(0, m(50), "B 1")
    ev = p.evaluate(0, m(80), 90, R)
    assert ev["nearest"]["n"] == 2 and not ev["ok"]
    assert p.undo() and len(p.rigs) == 1 and "borrado" in p.message()
    p.set_body("B 2"); assert p.rigs == []                                                   # otro planeta: se borran


if __name__ == "__main__":
    test_gestos(); test_distancias(); print("OK test_rigs")
