"""Plataformas recogidas seguidas (sin pausa) deben contarse por separado."""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "SkullMining"))
import skull_analysis as A

R = 1_500_000.0
M_PER_DEG = R * math.pi / 180


def rig_burst(t0, lat, lon, n, typ="monazite"):
    return [{"t": t0 + i * 1.2, "type": typ, "lat": lat, "lon": lon + i * 1e-6} for i in range(n)]


def test_tres_plataformas_seguidas():
    lat, lon = 10.0, 20.0
    d = 50 / M_PER_DEG
    ref = rig_burst(0, lat, lon, 11) + rig_burst(18, lat, lon + d, 12) + rig_burst(36, lat, lon + 2 * d, 10)
    cols = A.collections_from_refined(ref, R)
    assert [c["tonnes"] for c in cols] == [11, 12, 10]
    s = A.summarize({"planet_radius": R, "track": [], "refined": ref})
    assert s["rigs"] == 3
    assert s["tonnes_per_collection"] <= 12


def test_tope_sin_posicion():
    ref = [{"t": i * 1.0, "type": "monazite", "lat": None, "lon": None} for i in range(24)]
    cols = A.collections_from_refined(ref, R)
    assert [c["tonnes"] for c in cols] == [12, 12]


def test_una_plataforma_normal():
    ref = rig_burst(0, 1.0, 1.0, 12)
    assert len(A.collections_from_refined(ref, R)) == 1


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("OK", k)
