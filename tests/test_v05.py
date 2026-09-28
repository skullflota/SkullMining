"""v0.5.0: datos en bruto, aviso de zona y detector de novedades del journal."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "SkullMining"))
import skull_analysis as A
import skull_tracker as T

SRV = T.FLAG_HAS_LATLONG | T.FLAG_IN_SRV


def status(ts, lat, lon, dest=None):
    e = {"timestamp": ts, "event": "Status", "Flags": SRV, "Latitude": lat, "Longitude": lon,
         "Altitude": 0, "BodyName": "Sis B 1", "PlanetRadius": 1500000.0}
    if dest:
        e["Destination"] = dest
    return e


def run(with_zone):
    out = []
    tr = T.Tracker(lambda k, d: out.append((k, d)))
    tr.on_journal("Yo", {"timestamp": "2026-10-01T10:00:00Z", "event": "Location", "StarSystem": "Sis", "SystemAddress": 1})
    dest = {"System": 1, "Body": 5, "Name": "$SAA_Unknown_Signal:#type=$PlanetaryMiningLocation_Name;:#index=4;"} if with_zone else None
    tr.on_status(status("2026-10-01T10:00:01Z", 10.0, 20.0, dest))
    tr.on_journal("Yo", {"timestamp": "2026-10-01T10:00:02Z", "event": "LaunchSRV", "SRVType": "mev_rhino"})
    tr.on_status(status("2026-10-01T10:00:03Z", 10.0, 20.0, dest))
    warn = tr.zone_missing(), tr.live_text()
    for i in range(12):
        tr.on_journal("Yo", {"timestamp": f"2026-10-01T10:01:{i:02d}Z", "event": "MiningRefined", "Type": "$monazite_name;"})
    tr.close_session("prueba")
    return warn, [d for k, d in out if k == "session"][0]


def test_aviso_sin_zona():
    (missing, text), rec = run(False)
    assert missing and "Zona desconocida" in text
    assert rec["zone_known"] is False


def test_datos_en_bruto():
    (missing, text), rec = run(True)
    assert not missing and "zona 4" in text
    raw = A.decode_refined(rec["refined_raw"], rec["session_start_t"])
    assert len(raw) == 12 and raw[0]["type"] == "monazite" and raw[0]["lat"] == 10.0
    assert rec["zone_known"] is True
    # con los datos en bruto se rehace el mismo resumen
    again = A.summarize({"planet_radius": rec["planet_radius_m"], "track": [], "refined": raw})
    assert again["rigs"] == rec["summary"]["rigs"] and again["tonnes"] == 12


def test_campos_nuevos():
    out = []
    tr = T.Tracker(lambda k, d: out.append((k, d)))
    for _ in range(10):
        tr.on_journal("Yo", {"timestamp": "2026-10-20T10:00:00Z", "event": "MiningRefined",
                             "Type": "$monazite_name;", "DepositID": 103})
    tr.on_journal("Yo", {"timestamp": "2026-10-20T10:00:00Z", "event": "ColonisationConstructionDepot"})
    tr.on_journal("Yo", {"timestamp": "2026-10-20T10:00:00Z", "event": "SurfaceDepositDepleted"})
    ev = [d["event"] for k, d in out if k == "event"]
    assert ev.count("CamposNuevos:MiningRefined:DepositID") == T.DISCOVERY_MAX_PER_RUN
    assert "SurfaceDepositDepleted" in ev and "ColonisationConstructionDepot" not in ev


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("OK", k)
