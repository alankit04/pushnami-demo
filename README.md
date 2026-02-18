# Landing Page Tracking System

This repository contains a four-service system for running a landing page experiment, tracking behavioral events, and administering both runtime feature toggles and experiment reporting.

## Architecture

The stack is built as four independently deployable services:

1. **Landing Service** (`landing-service`)
   - Serves the user-facing landing page.
   - Requests a stable variant assignment from the A/B service.
   - Applies server-configurable feature toggles.
   - Sends user interaction events to the metrics service.

2. **A/B Assignment Service** (`ab-service`)
   - Assigns visitors consistently to variant `A` or `B`.
   - Persists assignments in SQLite to maintain stable repeat experiences.
   - Exposes admin APIs for updating experiment/feature toggle settings.

3. **Metrics Service** (`metrics-service`)
   - Ingests page interaction events.
   - Persists events in SQLite.
   - Exposes aggregate stats APIs grouped by variant and event type.
   - Computes simple conversion metrics (`form_submit` / `page_view`).

4. **Admin App** (`admin-app`)
   - Hosts a web dashboard for:
     - Editing feature toggles and experiment enablement.
     - Viewing event aggregates and conversion-oriented performance metrics.

## Run the system

### Prerequisites
- Docker
- Docker Compose v2+

### Start everything

```bash
docker compose up --build
```

### Access URLs
- Landing page: http://localhost:8080
- Admin dashboard: http://localhost:8081
- Metrics API: http://localhost:5001/stats
- A/B API health: http://localhost:5002/health

## Design decisions

- **Service boundaries**: each responsibility is in a separate process for clear ownership and independent evolution.
- **Persistence**: SQLite is used for both assignment and event storage to avoid in-memory data loss while keeping setup minimal.
- **Consistent assignments**: deterministic assignment on first request + persistence ensures repeat visitors maintain the same variant.
- **Feature toggle control plane**: toggles are centralized in the A/B service and consumed by the landing page in real time.
- **Dependency minimization**: services are implemented using Python standard library + SQLite to reduce supply-chain risk and improve reproducibility in restricted environments.

## Production-readiness considerations

- API input validation and structured error responses on ingest/assignment paths.
- Process isolation through separate services and explicit interfaces.
- Persistent storage for critical data (assignments + events) via mounted volumes.
- Container hardening basics (non-root users, minimal images).
- Health endpoints for all services.
- Admin controls for live behavior changes without redeploying.

## Notes

- CORS is intentionally open for local multi-origin development.
- Assignment persistence means changing `experimentEnabled` does not rewrite existing users; it affects new assignments.
