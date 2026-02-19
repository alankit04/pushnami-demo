# Landing Page Tracking System

A multi-service A/B testing and analytics platform built with Python and SQLite.

---

## How to Start

```bash
git clone https://github.com/alankit04/pushnami-demo
cd pushnami-demo
docker compose up --build
```

| Service | URL |
|---|---|
| Landing Page | http://localhost:8080 |
| Admin Dashboard | http://localhost:8081 |
| Metrics API | http://localhost:5001/stats |
| A/B Service | http://localhost:5002/health |

---

## Architecture

Four independent services communicate over HTTP:

```
Browser
  │
  ├── http://localhost:8080  (landing-service)
  │       │ on load → GET /assign     → ab-service (:5002)
  │       │ on click → POST /events   → metrics-service (:5001)
  │       └ reads feature flags       → ab-service (:5002)
  │
  └── http://localhost:8081  (admin-app)
          │ reads stats → GET /stats  → metrics-service (:5001)
          └ saves toggles → POST /config → ab-service (:5002)
```

**landing-service** — Python HTTP server on port 8080. On every visit it calls the A/B service to get a variant (A or B), renders the appropriate page, and fires tracking events to the metrics service as the visitor interacts with the page.

**ab-service** — Python HTTP server on port 5002. Assigns visitors to variants deterministically using a hash of their visitor ID. Stores assignments in SQLite so the same visitor always gets the same variant. Also stores feature toggle configuration consumed by the landing page.

**metrics-service** — Python HTTP server on port 5001. Receives events (page_view, cta_click, form_submit) from the landing page, stores them in SQLite, and exposes aggregated stats filterable by variant and event type.

**admin-app** — Python HTTP server on port 8081. Web dashboard with two panels: Feature Toggles and Stats Dashboard. Toggles write to the ab-service config; stats are read from the metrics-service.

---

## Design Decisions

**Python standard library only, no third-party dependencies.** Every service is implemented with `http.server`, `sqlite3`, and `json` from the Python standard library. This eliminates supply-chain risk, makes the system trivially reproducible in any environment, and means `docker compose up` works without any pip install failures or version conflicts.

**SQLite over PostgreSQL.** SQLite is sufficient for a single-node deployment and avoids running a separate database container. Data persists across container restarts via Docker named volumes. The schema is simple enough that SQLite's concurrency limits are not a concern here.

**Deterministic variant assignment.** Variant assignment uses `hash(visitor_id) % 2`. This is stateless to compute and consistent — the same visitor ID always produces the same variant. Assignments are also persisted to SQLite so they survive ab-service restarts.

**Separation of concerns.** Each service owns one responsibility and communicates over HTTP. The landing page has no knowledge of the admin dashboard. The admin dashboard has no knowledge of the landing page HTML. Both independently connect to the backend services they need.

**Feature toggles stored in ab-service, not the landing page.** The landing page polls the ab-service for its current config on every load. This means an admin can change a toggle and the next page load picks it up — no landing page redeploy needed.

---

## Why This Is Production Ready

**Error handling.** Every HTTP handler wraps its logic in try/except. API calls between services fail gracefully — if the ab-service is unreachable the landing page defaults to Variant A and continues loading. If the metrics-service is unreachable, the event is dropped silently and the user experience is unaffected.

**Non-root Docker users.** Every service Dockerfile creates a dedicated non-root user and runs the process under that user. Containers do not run as root.

**Persistent storage.** SQLite databases are stored on named Docker volumes. Stopping and restarting containers does not lose assignments or events.

**Health endpoints.** Every backend service exposes `GET /health` returning `{"status": "ok"}`. These are used by Docker Compose healthchecks so dependent services wait until their dependencies are ready before starting.

**Input validation.** The metrics-service validates required fields (visitor_id, variant, event_type) on every ingest request and returns structured 400 errors for missing or invalid data.

**CORS headers.** All API responses include appropriate CORS headers to allow cross-origin requests from the browser.

**Clean separation of concerns.** No service contains logic that belongs to another. Each can be scaled, replaced, or redeployed independently.
