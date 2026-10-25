"""v0.6.0: formulario de sitio (mark) y sugerencias."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "SkullMining"))
import skull_tracker as T

SRV = T.FLAG_HAS_LATLONG | T.FLAG_IN_SRV


def st(ts, lat, lon, flags=SRV):
    return {"timestamp": ts, "event": "Status", "Flags": flags, "Latitude": lat, "Longitude": lon,
            "Altitude": 0, "BodyName": "Sis B 1", "PlanetRadius": 1500000.0,
            "Destination": {"System": 1, "Body": 5, "Name": "$SAA_Unknown_Signal:#type=$PlanetaryMiningLocation_Name;:#index=7;"}}


def test_formulario():
    out = []
    tr = T.Tracker(lambda k, d: out.append((k, d)))
    tr.on_journal("Yo", {"timestamp": "2026-10-13T10:00:00Z", "event": "Location", "StarSystem": "Sis", "SystemAddress": 1})
    assert "superficie" in tr.mark_site(None, 2, "monazite", "Alta", "Media")   # sin posición
    tr.on_status(st("2026-10-13T10:00:01Z", 10.0, 20.0))
    tr.on_journal("Yo", {"timestamp": "2026-10-13T10:00:02Z", "event": "LaunchSRV", "SRVType": "mev_rhino"})
    for i in range(12):
        tr.on_journal("Yo", {"timestamp": f"2026-10-13T10:01:{i:02d}Z", "event": "MiningRefined", "Type": "$monazite_name;"})
    sug = tr.suggest()
    assert sug["zone"] == 7 and sug["type"] == "monazite" and sug["rigs"] == 1
    assert "Elige" in tr.mark_site(7, 1, None, None, None)
    msg = tr.mark_site(None, 3, "monazite", "Media", "Alta")
    assert msg.startswith("Enviado"), msg
    rec = [d for k, d in out if k == "mark"][0]
    assert rec["zone"] == 7 and rec["rigs"] == 3 and rec["amount"] == "Media" and rec["density"] == "Alta"
    assert rec["session_tonnes"] == 12 and rec["lat"] == 10.0 and rec["planet_radius_m"] == 1500000.0
    # en la nave aterrizada también vale
    tr.on_status(st("2026-10-13T10:05:00Z", 10.0, 20.0, T.FLAG_HAS_LATLONG | (1 << 1)))
    assert tr.mark_site(7, 0, "iridium", None, None).startswith("Enviado")
    # v0.8.0: "Solo cabe 1" sin desplegar ningún taladro
    msg = tr.mark_site(7, 0, "iridium", None, None, one_rig=True)
    assert "solo cabe 1" in msg, msg
    rec = [d for k, d in out if k == "mark"][-1]
    assert rec["one_rig"] is True and rec["rigs"] == 1
    assert [d for k, d in out if k == "mark"][0]["one_rig"] is False


if __name__ == "__main__":
    test_formulario(); print("OK test_formulario")
