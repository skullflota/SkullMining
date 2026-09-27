"""Tiempos reales de refinado (sesión de Adder, 27-sep-2026, Pegasi Sector JN-S b4-7 B 4 a)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "SkullMining"))
import skull_analysis as A  # noqa: E402
import skull_tracker as T  # noqa: E402

JOURNAL = os.path.join(HERE, "journal_real_rhino.log")


def load_refined():
    out = []
    for line in open(JOURNAL, encoding="utf-8"):
        e = json.loads(line)
        if e["event"] == "MiningRefined":
            out.append({"t": T.parse_ts(e["timestamp"]), "type": T.clean_type(e["Type"]), "lat": 0.0, "lon": 0.0})
    return out


def test_collections():
    cols = A.collections_from_refined(load_refined())
    got = [(c["main_type"], c["tonnes"]) for c in cols]
    assert got == [("thortveitite", 11), ("thorium", 12), ("thortveitite", 11), ("thorium", 11)], got
    # Posiciones inventadas: cada mineral en su plataforma, a 120 m
    ref = load_refined()
    for r in ref:
        if r["type"] == "thorium":
            r["lat"] = 0.0074
    rigs = A.cluster_rigs(ref, 925274.0625)
    assert len(rigs) == 2 and all(r["collections"] == 2 for r in rigs), rigs
    return cols, rigs


if __name__ == "__main__":
    cols, rigs = test_collections()
    for r in rigs:
        print(r["main_type"], r["tonnes"], "t en", r["collections"], "recogidas; t/recogida", r["tonnes_per_collection"])
    print("OK")
