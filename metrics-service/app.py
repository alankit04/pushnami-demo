import json
import os
import sqlite3
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_PATH = os.getenv("DB_PATH", "/data/metrics.sqlite")
PORT = int(os.getenv("PORT", "5001"))
MAX_EVENTS_RESPONSE = int(os.getenv("MAX_EVENTS_RESPONSE", "200"))
from urllib.parse import urlparse

DB_PATH = os.getenv("DB_PATH", "/data/metrics.sqlite")
PORT = int(os.getenv("PORT", "5001"))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(get_conn()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                variant TEXT NOT NULL,
                event_type TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def build_filters(query):
    clauses = []
    params = []
    variant = (query.get("variant", [""])[0]).strip()
    event_type = (query.get("event_type", [""])[0]).strip()

    if variant:
        clauses.append("variant = ?")
        params.append(variant)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params, variant, event_type


def compute_stats(query):
    where_sql, params, variant_filter, event_type_filter = build_filters(query)

def compute_stats():
    with closing(get_conn()) as conn:
        by_variant = [
            dict(row)
            for row in conn.execute(
                f"SELECT variant, COUNT(*) AS count FROM events {where_sql} GROUP BY variant ORDER BY variant",
                params,
                "SELECT variant, COUNT(*) AS count FROM events GROUP BY variant ORDER BY variant"
            ).fetchall()
        ]
        by_event = [
            dict(row)
            for row in conn.execute(
                f"SELECT event_type, COUNT(*) AS count FROM events {where_sql} GROUP BY event_type ORDER BY event_type",
                params,
                "SELECT event_type, COUNT(*) AS count FROM events GROUP BY event_type ORDER BY event_type"
            ).fetchall()
        ]
        matrix = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT variant, event_type, COUNT(*) AS count
                FROM events
                {where_sql}
                GROUP BY variant, event_type
                ORDER BY variant, event_type
                """,
                params,
            ).fetchall()
        ]
        recent = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT id, visitor_id, variant, event_type, metadata, created_at
                FROM events
                {where_sql}
                ORDER BY id DESC
                LIMIT ?
                """,
                [*params, MAX_EVENTS_RESPONSE],
                """
                SELECT variant, event_type, COUNT(*) AS count
                FROM events
                GROUP BY variant, event_type
                ORDER BY variant, event_type
                """
            ).fetchall()
        ]

    page_views = {
        row["variant"]: row["count"] for row in matrix if row["event_type"] == "page_view"
    }
    submissions = {
        row["variant"]: row["count"] for row in matrix if row["event_type"] == "form_submit"
    }

    conversion = []
    for variant in sorted(set(page_views.keys()) | set(submissions.keys())):
        views = page_views.get(variant, 0)
        submits = submissions.get(variant, 0)
        conversion.append(
            {
                "variant": variant,
                "page_views": views,
                "form_submits": submits,
                "conversion_rate": round((submits / views) * 100, 2) if views else 0,
            }
        )

    return {
        "filters": {
            "variant": variant_filter or None,
            "event_type": event_type_filter or None,
        },
        "totalsByVariant": by_variant,
        "totalsByEventType": by_event,
        "variantEventBreakdown": matrix,
        "conversion": conversion,
        "recentEvents": recent,
    }


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            return self._send_json(200, {"status": "ok"})
        if parsed.path == "/stats":
            query = parse_qs(parsed.query)
            return self._send_json(200, compute_stats(query))
            return self._send_json(200, compute_stats())
        return self._send_json(404, {"error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/events":
            return self._send_json(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return self._send_json(400, {"error": "invalid JSON"})

        required = ["visitor_id", "variant", "event_type"]
        if not all(payload.get(k) for k in required):
            return self._send_json(400, {"error": "visitor_id, variant, and event_type are required"})

        with closing(get_conn()) as conn:
            conn.execute(
                "INSERT INTO events(visitor_id, variant, event_type, metadata) VALUES (?, ?, ?, ?)",
                (
                    str(payload["visitor_id"]).strip(),
                    str(payload["variant"]).strip(),
                    str(payload["event_type"]).strip(),
                    payload["visitor_id"],
                    payload["variant"],
                    payload["event_type"],
                    json.dumps(payload.get("metadata", {})),
                ),
            )
            conn.commit()

        return self._send_json(202, {"status": "accepted"})


if __name__ == "__main__":
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()
