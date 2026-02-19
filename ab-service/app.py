import hashlib
import json
import os
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_PATH = os.getenv("DB_PATH", "/data/ab.sqlite")
PORT = int(os.getenv("PORT", "5002"))

DEFAULT_CONFIG = {
    "experimentEnabled": True,
    "showPromoSection": True,
    "enableSignupForm": True,
    "alternateCtaDestination": False,
}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(get_conn()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assignments (
                visitor_id TEXT PRIMARY KEY,
                variant TEXT NOT NULL,
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        for key, value in DEFAULT_CONFIG.items():
            conn.execute(
                "INSERT OR IGNORE INTO config(key, value) VALUES (?, ?)",
                (key, str(value).lower()),
            )
        conn.commit()


def config_dict():
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT key, value FROM config").fetchall()
    return {r["key"]: r["value"] == "true" for r in rows}


def choose_variant(visitor_id: str) -> str:
    digest = hashlib.sha256(visitor_id.encode("utf-8")).hexdigest()
    return "A" if int(digest[-1], 16) % 2 == 0 else "B"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,PUT,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,PUT,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send_json(200, {"status": "ok"})

        if parsed.path == "/config":
            return self._send_json(200, config_dict())

        if parsed.path == "/admin/config":
            return self._send_json(200, config_dict())

        if parsed.path == "/assign":
            query = parse_qs(parsed.query)
            visitor_id = (query.get("visitor_id", [""])[0]).strip()
            preferred_variant = (query.get("preferred_variant", [""])[0]).strip().upper()
            if not visitor_id:
                return self._send_json(400, {"error": "visitor_id is required"})
            if preferred_variant and preferred_variant not in {"A", "B"}:
                return self._send_json(400, {"error": "preferred_variant must be A or B"})
            if not visitor_id:
                return self._send_json(400, {"error": "visitor_id is required"})

            cfg = config_dict()
            with closing(get_conn()) as conn:
                row = conn.execute(
                    "SELECT variant FROM assignments WHERE visitor_id = ?", (visitor_id,)
                ).fetchone()

                if row:
                    variant = row["variant"]
                else:
                    if preferred_variant in {"A", "B"}:
                        variant = preferred_variant
                    else:
                        variant = (
                            "A"
                            if not cfg.get("experimentEnabled", True)
                            else choose_variant(visitor_id)
                        )
                    variant = (
                        "A"
                        if not cfg.get("experimentEnabled", True)
                        else choose_variant(visitor_id)
                    )
                    conn.execute(
                        "INSERT INTO assignments(visitor_id, variant) VALUES (?, ?)",
                        (visitor_id, variant),
                    )
                    conn.commit()

            return self._send_json(
                200,
                {
                    "visitor_id": visitor_id,
                    "variant": variant,
                    "experimentEnabled": cfg.get("experimentEnabled", True),
                    "preferredVariantApplied": bool(preferred_variant in {"A", "B"} and not row),
                },
            )

        return self._send_json(404, {"error": "not found"})

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path != "/admin/config":
            return self._send_json(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "invalid JSON"})

        cfg = config_dict()
        allowed = set(cfg.keys())
        with closing(get_conn()) as conn:
            for key, value in payload.items():
                if key in allowed and isinstance(value, bool):
                    conn.execute(
                        "UPDATE config SET value = ? WHERE key = ?",
                        (str(value).lower(), key),
                    )
            conn.commit()

        return self._send_json(200, config_dict())


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
