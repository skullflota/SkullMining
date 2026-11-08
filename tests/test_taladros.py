"""v0.9.3: llegar al mismo taladro desde lados distintos no debe contar dos taladros."""
import math, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "SkullMining"))
import skull_analysis as A

R = 1500000.0
m = lambda x: x / (R * math.pi / 180)


def col(t, lat, lon, n=4, typ="osmium"):
    return [{"t": t + i, "type": typ, "lat": lat, "lon": lon} for i in range(n)]


def test_mismo_taladro_por_dos_lados():
    ref = col(0, 0, m(20)) + col(300, 0, m(-20)) + col(600, 0, m(70)) + col(900, 0, m(20))
    rigs = A.cluster_rigs(ref, R)
    assert len(rigs) == 2 and sorted(r["collections"] for r in rigs) == [1, 3]


def test_taladros_reales_al_minimo():
    assert len(A.cluster_rigs(col(0, 0, 0) + col(300, 0, m(47)) + col(600, 0, 0), R)) == 2


def test_minerales_distintos_cerca():
    assert len(A.cluster_rigs(col(0, 0, 0) + col(300, 0, m(10), typ="iridium"), R)) == 2


if __name__ == "__main__":
    test_mismo_taladro_por_dos_lados(); test_taladros_reales_al_minimo(); test_minerales_distintos_cerca()
    print("OK test_taladros")
