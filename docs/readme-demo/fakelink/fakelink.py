"""A stand-in for two printers' PrusaLink, for the README demo: port 8081 prints, 8082 is idle."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATES = {8081: "PRINTING", 8082: "IDLE"}
JOB = {
    "id": 101, "state": "PRINTING", "progress": 42.0, "time_remaining": 5040, "time_printing": 3600,
    "file": {"name": "DEMO_P~1.BGC", "display_name": "demo_part.bgcode", "path": "/usb",
             "refs": {"download": "/usb/DEMO_P~1.BGC"}},
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body=None):
        data = b"" if body is None else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    def do_GET(self):
        state = STATES.get(self.server.server_address[1], "IDLE")
        path = self.path.split("?")[0]
        printing = state == "PRINTING"
        if path == "/api/v1/status":
            body = {"printer": {"state": state, "temp_nozzle": 215.0 if printing else 24.0,
                                "target_nozzle": 215.0 if printing else 0.0,
                                "temp_bed": 60.0 if printing else 23.0, "target_bed": 60.0 if printing else 0.0}}
            if printing:
                body["job"] = {"id": JOB["id"], "progress": JOB["progress"],
                               "time_remaining": JOB["time_remaining"], "time_printing": JOB["time_printing"]}
            return self._send(200, body)
        if path == "/api/v1/job":
            return self._send(200, JOB) if printing else self._send(204)
        if path == "/api/printer":
            return self._send(200, {"state": {"text": "Printing" if printing else "Operational",
                                              "flags": {"printing": printing, "paused": False}}})
        return self._send(404, {"message": "not found"})

    def log_message(self, *args):
        pass


for port in STATES:
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
threading.Event().wait()
