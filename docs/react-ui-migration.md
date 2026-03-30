# React UI Migration

This document turns the Streamlit-to-React migration into an implementation checklist and records the target architecture for the first delivery slices.

## Goals

- Replace the DPS Streamlit dashboard with a React app route.
- Replace the FEED Streamlit client UI with a React app route.
- Keep secrets and Cosmos access on the server side.
- Migrate incrementally so the new UI can run alongside the current Streamlit services until parity is acceptable.

## Target Architecture

- `src/ui/`
  - Vite + React app
  - HeroUI component library
  - Browser-only config and API client
- `src/app/modules/UI_API/`
  - FastAPI backend for all UI data and UI-triggered mutations
  - Uses existing Python modules for Cosmos access and pipeline execution

## Concrete Checklist

### Phase 1: Backend seam

- [x] Create `UI_API` FastAPI module.
- [x] Add health route.
- [x] Add client/feed read endpoints.
- [x] Add ops/dashboard read endpoints.
- [x] Add manual pipeline upload and sample-run endpoints.
- [x] Keep all Cosmos credentials server-side.

### Phase 2: Frontend scaffold

- [x] Create `src/ui` Vite project structure.
- [x] Add React Router shell.
- [x] Add HeroUI-compatible CSS and dependencies.
- [x] Add typed API client helpers.
- [x] Add `/ops` and `/clients` route skeletons.

### Phase 3: Runtime integration

- [x] Add `ui-api` container to Docker Compose.
- [x] Add `ui` container to Docker Compose.
- [x] Proxy `/api` from the frontend container to the backend API.
- [ ] Update README runbook after parity improves.

### Phase 4: UI parity work

- [ ] Port DPS metrics, tables, and timeline interactions.
- [ ] Port FEED portfolio summary and insights.
- [ ] Replace Streamlit refresh controls with polling in React.
- [ ] Improve upload flow state, progress, and error handling.
- [ ] Add pagination, filters, and richer detail views.

### Phase 5: Cleanup

- [ ] Remove Streamlit containers and dependencies after validation.
- [ ] Remove duplicated query logic.
- [ ] Normalize settings loading across FEED, DPS, and UI API.

## Backend Endpoint Contract

### Read endpoints

- `GET /api/health`
- `GET /api/clients`
- `GET /api/clients/{client_id}/portfolio`
- `GET /api/clients/{client_id}/insights`
- `GET /api/ops/metrics`
- `GET /api/ops/news?limit=50`
- `GET /api/ops/news/{news_id}`
- `GET /api/ops/insights?limit=10`

### Mutation endpoints

- `POST /api/ops/pipeline/upload`
- `POST /api/ops/pipeline/sample`

## Notes

- The original Streamlit apps remain the source of truth for missing UI details during the migration.
- The current repo does not include a DPS sample folder under `src/app/modules/DPS/news_raw`, so the sample endpoint is implemented defensively and returns a clear error when that directory is missing.
