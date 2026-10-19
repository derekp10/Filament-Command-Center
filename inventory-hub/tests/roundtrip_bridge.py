"""The server half of tests/roundtrip_harness.py (Group 40.3 review, C6; adopted
from the review's C-contract probes): the REAL Flask app and the REAL move
engine over the hermetic move_engine_harness fakes, answering the node-vm
driver over stdin / stdout. No network, no container, nothing written outside
the run's own directory (the cwd).

One JSON request per line in, one '@@'-prefixed JSON answer per line out.
  Request: {"id": n, "method": "GET"|"POST", "url": "/api/...", "body": {...}|null}
  Control: url "/__ctl/<op>":
    repoint         {"box", "slot", "to"}           rebind a box slot (None unbinds)
    printing        {"printers": [...]}             which printers PRINT, for every probe
    move_probe_fail {"printers": [...]}             the MOVE's probe of these fails (None,
                                                    fail open) while /api/printer_state answers
    move            {"sid", "location", "extra"?}   set a spool's record (another user)
    state           {}                              spools, writes, bindings, buffer, logs
Every door request is answered by app.test_client() inside move_engine_harness
.run_move, so the probe is patched below the memo and locations.json is a live
LocationsStore. argv[1] = inventory-hub, argv[2] = the setup JSON (rows,
printer_map, spools, printing, move_probe_fail, buffer). Not a test module.
"""
import copy
import json
import os
import sys

HUB = sys.argv[1]
with open(sys.argv[2], encoding="utf-8") as _f:
    SETUP = json.load(_f)
sys.path.insert(0, HUB)
sys.path.insert(0, os.path.join(HUB, "tests"))

import logging  # noqa: E402
logging.disable(logging.CRITICAL)

import app as app_module  # noqa: E402
import logic  # noqa: E402
import state  # noqa: E402
from move_engine_harness import FakeSpoolman, LocationsStore, _probe_for, run_move  # noqa: E402

app_module.app.config["TESTING"] = True
client = app_module.app.test_client()

PM = SETUP["printer_map"]
store = LocationsStore(SETUP["rows"])
sm = FakeSpoolman({int(k): v for k, v in SETUP["spools"].items()})
printing = set(SETUP.get("printing") or [])
move_probe_fail = set(SETUP.get("move_probe_fail") or [])
state.RECENT_LOGS, state.UNDO_STACK = [], []
state.GLOBAL_BUFFER = copy.deepcopy(SETUP.get("buffer") or [])
requests_seen = []


def control(op, body):
    global printing, move_probe_fail
    body = body or {}
    if op == "repoint":
        row = store.row(body["box"])
        targets = row.setdefault("extra", {}).setdefault("slot_targets", {})
        if body.get("to") is None:
            targets.pop(str(body["slot"]), None)
        else:
            targets[str(body["slot"])] = body["to"]
        return {"ok": True, "bindings": targets}
    if op == "printing":
        printing = set(body.get("printers") or [])
        return {"ok": True}
    if op == "move_probe_fail":
        move_probe_fail = set(body.get("printers") or [])
        return {"ok": True}
    if op == "move":
        rec = sm.spools.setdefault(int(body["sid"]), {"location": "", "extra": {}})
        rec["location"] = body["location"]
        if "extra" in body:
            rec["extra"] = copy.deepcopy(body["extra"])
        return {"ok": True}
    if op == "state":
        return {
            "spools": {str(k): v for k, v in sm.spools.items()},
            "writes": sm.writes,
            "bindings": {r["LocationID"]: logic.locations_db.bindings_from_row(r)
                         for r in store.rows if r.get("Type") == "Dryer Box"},
            "buffer": state.GLOBAL_BUFFER,
            "logs": [str(e.get("msg")) for e in state.RECENT_LOGS],
            "requests": requests_seen,
        }
    return {"error": f"unknown control {op}"}


def handle(req):
    url, method, body = req["url"], req.get("method") or "GET", req.get("body")
    if url.startswith("/__ctl/"):
        return {"status": 200, "body": control(url[len("/__ctl/"):], body)}
    requests_seen.append({"method": method, "url": url, "body": body})
    if url.startswith("/api/printer_state/"):
        th = url[len("/api/printer_state/"):].strip().upper()
        info = PM.get(th)
        if not info:
            return {"status": 200, "body": {"known": False, "reason": "not_in_printer_map"}}
        active = info["printer_name"] in printing
        return {"status": 200, "body": {"known": True, "state": "PRINTING" if active else "IDLE",
                                        "is_active": active, "printer_name": info["printer_name"]}}
    if url == "/api/locations":
        return {"status": 200, "body": copy.deepcopy(store.rows)}
    if url.startswith("/api/log_event") or url.startswith("/api/state/buffer"):
        return {"status": 200, "body": {"success": True}}
    base = _probe_for(printing)

    def probe(probe_url, printer_name):
        if printer_name in move_probe_fail:
            return None
        return base(probe_url, printer_name)
    resp = run_move(sm, probe=probe, store=store, printer_map=PM,
                    call=lambda: client.open(url, method=method, json=body))
    try:
        data = resp.get_json()
    except Exception:
        data = None
    return {"status": resp.status_code, "body": data}


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    req = json.loads(line)
    try:
        out = handle(req)
    except Exception as e:  # surface it to the driver
        import traceback
        out = {"status": 599, "body": {"bridge_error": repr(e), "tb": traceback.format_exc()}}
    out["id"] = req["id"]
    sys.stdout.write("@@" + json.dumps(out, default=str) + "\n")
    sys.stdout.flush()
