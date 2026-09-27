"""Sesión simulada con el Rhino: 4 plataformas, terreno con desnivel y rodeos."""
import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "SkullMining"))

import skull_analysis as A  # noqa: E402
import skull_tracker as T  # noqa: E402

R = 1_500_000.0
BODY = "Skull Test 3 a"
T0 = datetime(2026, 9, 27, 18, 0, 0, tzinfo=timezone.utc)


def ts(sec):
    return (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")


def offset(lat, lon, dn, de):
    """Desplaza dn metros al norte y de metros al este."""
    dlat = math.degrees(dn / R)
    dlon = math.degrees(de / (R * math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def status(sec, lat, lon, alt, srv=True):
    flags = T.FLAG_HAS_LATLONG | T.FLAG_ALT_FROM_AVG_RADIUS | (T.FLAG_IN_SRV if srv else T.FLAG_IN_MAINSHIP)
    return {"timestamp": ts(sec), "event": "Status", "Flags": flags, "Flags2": 0, "Latitude": lat,
            "Longitude": lon, "Altitude": alt, "Heading": 0, "BodyName": BODY, "PlanetRadius": R}


def build():
    out = []
    tr = T.Tracker(lambda k, d: out.append((k, d)))
    tr.on_journal("CMDR Adder", {"timestamp": ts(0), "event": "FSDJump", "StarSystem": "Skull Test",
                                 "SystemAddress": 123, "StarPos": [1, 2, 3]})
    tr.on_journal("CMDR Adder", {"timestamp": ts(5), "event": "Scan", "BodyName": BODY, "BodyID": 7,
                                 "PlanetClass": "Rocky body", "SurfaceGravity": 1.9, "SurfaceTemperature": 180.0,
                                 "Radius": R, "Landable": True})
    tr.on_journal("CMDR Adder", {"timestamp": ts(6), "event": "SAASignalsFound", "BodyName": BODY,
                                 "Signals": [{"Type": "$PlanetaryMiningLocation_Name;", "Count": 2}]})
    lat0, lon0 = 10.0, 20.0
    tr.on_status(status(9, lat0, lon0, 530, srv=False))  # nave en vuelo estacionario
    tr.on_journal("CMDR Adder", {"timestamp": ts(10), "event": "LaunchSRV", "SRVType": "rhino"})
    # Evento desconocido del Rhino (simulado)
    tr.on_journal("CMDR Adder", {"timestamp": ts(11), "event": "MiningRigDeployed", "RigID": 1})

    # 4 plataformas en cuadrado de 150 m; se conduce con zigzag y colinas
    rigs = [(0, 0), (0, 150), (150, 150), (150, 0)]
    sec = 12
    pos = (0.0, 0.0)
    for i, (n, e) in enumerate(rigs + rigs):  # dos vueltas de recogida
        steps = 30
        for s in range(1, steps + 1):
            f = s / steps
            dn = pos[0] + (n - pos[0]) * f
            de = pos[1] + (e - pos[1]) * f
            wig = 25 * math.sin(f * math.pi * 3)  # rodeo lateral
            if n != pos[0]:
                de += wig
            else:
                dn += wig
            alt = 500 + 30 * math.sin((dn + de) / 40)
            la, lo = offset(lat0, lon0, dn, de)
            tr.on_status(status(sec, la, lo, alt))
            sec += 2
        pos = (n, e)
        # recogida: 6 t refinadas en esa plataforma
        for k in range(6):
            typ = "$monazite_name;" if k < 4 else "$platinum_name;"
            tr.on_journal("CMDR Adder", {"timestamp": ts(sec), "event": "MiningRefined", "Type": typ,
                                         "Type_Localised": "Monacita" if k < 4 else "Platino"})
            sec += 1
        if i == 3:
            sec += 600  # espera a que las plataformas vuelvan a llenarse
    tr.on_journal("CMDR Adder", {"timestamp": ts(sec + 5), "event": "DockSRV", "SRVType": "rhino"})
    tr.on_journal("CMDR Adder", {"timestamp": ts(sec + 900), "event": "MarketSell", "Type": "$monazite_name;",
                                 "Type_Localised": "Monacita", "Count": 32, "SellPrice": 265000,
                                 "TotalSale": 8480000, "MarketID": 99})
    return out


def test_session():
    out = build()
    kinds = [k for k, _ in out]
    assert "session" in kinds and "sale" in kinds and "event" in kinds and "body" in kinds, kinds
    sess = [d for k, d in out if k == "session"][0]
    s = sess["summary"]
    assert s["rigs"] == 4, s["rigs"]
    assert all(r["collections"] == 2 for r in s["rig_list"]), s["rig_list"]
    assert s["tonnes"] == 48
    assert 140 < s["spacing"]["nn_mean_m"] < 160, s["spacing"]
    assert 580 < s["route"]["loop_m"] < 620, s["route"]
    assert s["sinuosity_median"] and s["sinuosity_median"] > 1.05
    assert s["gain_per_km"] and s["gain_per_km"] > 0
    assert sess["unknown_events"] == ["MiningRigDeployed"]
    json.dumps(sess)  # serializable
    return out


if __name__ == "__main__":
    out = test_session()
    sess = [d for k, d in out if k == "session"][0]
    s = dict(sess["summary"])
    s.pop("rig_list")
    print(json.dumps(s, indent=1, ensure_ascii=False))
    with open(os.path.join(HERE, "payloads.json"), "w", encoding="utf-8") as f:
        json.dump(out, f)
    print("OK")
