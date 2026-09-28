"""Zonas de minería y estado del sitio (v0.4.0)."""
import json
import math
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "SkullMining"))
import skull_tracker as T  # noqa: E402

R = 925274.0625
SYS, ADDR, BODY, BID = "Pegasi Sector JN-S b4-7", 16061164299681, "Pegasi Sector JN-S b4-7 B 4 a", 13
T0 = datetime(2026, 9, 28, 18, 0, 0, tzinfo=timezone.utc)


def ts(sec):
    return (T0 + timedelta(seconds=sec)).strftime("%Y-%m-%dT%H:%M:%SZ")


def off(lat, lon, dn, de):
    return lat + math.degrees(dn / R), lon + math.degrees(de / (R * math.cos(math.radians(lat))))


def dest(idx):
    return {"System": ADDR, "Body": BID, "Name": f"$SAA_Unknown_Signal:#type=$PlanetaryMiningLocation_Name;:#index={idx};",
            "Name_Localised": f"Planetary Mining Location Signal ({idx})"}


def st(sec, lat=None, lon=None, srv=True, destination=None):
    e = {"timestamp": ts(sec), "event": "Status", "Flags": T.FLAG_IN_MAINSHIP, "Flags2": 0}
    if lat is not None:
        e.update({"Flags": T.FLAG_HAS_LATLONG | (T.FLAG_IN_SRV if srv else T.FLAG_IN_MAINSHIP),
                  "Latitude": lat, "Longitude": lon, "Altitude": 0, "BodyName": BODY, "PlanetRadius": R})
    if destination:
        e["Destination"] = destination
    return e


def refine(tr, sec, typ, n=11):
    for k in range(n):
        tr.on_journal("CMDR Adder", {"timestamp": ts(sec + k), "event": "MiningRefined", "Type": f"${typ}_name;"})


def run():
    tmp = tempfile.mkdtemp()
    out = []
    tr = T.Tracker(lambda k, d: out.append((k, d)), live_path=os.path.join(tmp, "live.json"),
                   state_path=os.path.join(tmp, "zones.json"))
    tr.on_journal("CMDR Adder", {"timestamp": ts(0), "event": "Location", "StarSystem": SYS, "SystemAddress": ADDR})
    tr.on_journal("CMDR Adder", {"timestamp": ts(1), "event": "SAASignalsFound", "BodyName": BODY, "BodyID": BID,
                                 "SystemAddress": ADDR, "Signals": [{"Type": "$PlanetaryMiningLocation_Name;", "Count": 7}]})
    # En órbita, fija la zona 3 (sin lat/lon todavía)
    tr.on_status(st(10, destination=dest(3)))
    assert tr.zone_target["index"] == 3 and tr.zone_target["body"] == BODY, tr.zone_target
    # Baja y despliega el Rhino en la zona 3
    z3 = (45.3082, -146.5652)
    tr.on_journal("CMDR Adder", {"timestamp": ts(20), "event": "LaunchSRV", "SRVType": "mev_rhino"})
    tr.on_status(st(21, *z3, destination=dest(3)))
    assert f"{BODY}|3" in tr.zone_anchors
    # Estando en superficie mira la zona 5 (no debe mover nada)
    tr.on_status(st(30, *off(*z3, 5, 5), destination=dest(5)))
    assert tr.current_zone() == 3, tr.current_zone()
    # Sitio de Thortveitita con 2 plataformas a 48 m y sitio de Torio a 400 m
    tr.on_status(st(40, *off(*z3, 0, 0)))
    refine(tr, 41, "thortveitite")
    tr.on_status(st(80, *off(*z3, 48, 0)))
    refine(tr, 81, "thortveitite")
    tr.on_status(st(120, *off(*z3, 400, 0)))
    refine(tr, 121, "thorium")
    # Marca el estado del sitio de Thortveitita
    tr.on_status(st(200, *off(*z3, 2, 1)))
    msg = tr.mark_state("bajo")
    assert "thortveitite" in msg, msg
    # Reinicio de EDMC: la zona fijada y las anclas se recuerdan
    tr2 = T.Tracker(lambda k, d: out.append((k, d)), live_path=os.path.join(tmp, "live.json"),
                    state_path=os.path.join(tmp, "zones.json"))
    assert tr2.zone_target["index"] == 5 and f"{BODY}|3" in tr2.zone_anchors
    tr2.status = tr.status
    assert tr2.current_zone() == 3
    tr.on_journal("CMDR Adder", {"timestamp": ts(300), "event": "DockSRV"})
    sess = [d for k, d in out if k == "session"][0]
    states = [d for k, d in out if k == "state"]
    return sess, states


def test_zonas():
    sess, states = run()
    sites = sess["summary"]["sites"]
    assert len(sites) == 2, sites
    assert all(s["zone"] == 3 for s in sites), [s.get("zone") for s in sites]
    th = [s for s in sites if s["main_type"] == "thortveitite"][0]
    assert th["rigs"] == 2, th
    assert sess["zones"] and sess["zones"][0]["index"] == 3, sess["zones"]
    assert states[0]["state"] == "bajo" and states[0]["zone"] == 3 and states[0]["type"] == "thortveitite"
    json.dumps(sess)


def test_aterrizaje():
    tmp = tempfile.mkdtemp()
    out = []
    tr = T.Tracker(lambda k, d: out.append((k, d)), state_path=os.path.join(tmp, "z.json"))
    tr.on_journal("C", {"timestamp": ts(0), "event": "Touchdown", "Body": BODY, "BodyID": BID, "SystemAddress": ADDR,
                        "Latitude": 45.12793, "Longitude": -146.599792,
                        "NearestDestination": "$SAA_Unknown_Signal:#type=$PlanetaryMiningLocation_Name;:#index=3;"})
    assert tr.zone_anchors[f"{BODY}|3"][3] == "aterrizaje"
    assert tr.zone_at(BODY, 45.13, -146.59, R) == 3
    assert tr.zone_at(BODY, 46.0, -146.59, R) is None or tr.zone_at(BODY, 46.0, -146.59, R) == 3


if __name__ == "__main__":
    test_zonas()
    test_aterrizaje()
    sess, states = run()
    print([(s["main_type"], s["rigs"], s["zone"]) for s in sess["summary"]["sites"]], sess["zones"], states[0])
    print("OK")
