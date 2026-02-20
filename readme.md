# Instalily Case Study: PartSelect AI Support Agent

## Overview
This project implements an AI support agent for PartSelect focused on **refrigerator** and **dishwasher** parts.

The assistant is designed to handle three core customer workflows:
1. **Part installation help** (example: `How can I install PS11752778?`)
2. **Compatibility checks** (example: `Does this part fit my model?`)
3. **Symptom troubleshooting** (example: `My ice maker is not working`)

The implementation prioritizes:
- practical product UX,
- retrieval accuracy,
- strict scope guardrails,
- extensibility for future intents and data growth.

## Problem Scope
PartSelect has a large parts catalog. This case study narrows scope to:
- Refrigerators and dishwashers only,
- ~364 part records,
- 1,200+ model compatibility mappings.

Out-of-scope appliance requests are intentionally deflected with clear guidance.

## Architecture (High Level)
The system is organized into four layers:

1. **Frontend (Next.js chat UI)**
- Acts as a typed presentation layer over a strict backend response schema rather than free-form text rendering.
- Renders intent-specific UI blocks (answer, install steps, compatibility cards, troubleshooting tips, suggested parts) so the user can act immediately.
- Maintains lightweight conversation state and context chips (model/appliance/part) to reduce re-entry friction in multi-turn support flows.
- Includes optimistic interaction patterns (quick actions, loading states, retry/export controls) while keeping business logic in backend handlers.

2. **API Layer (FastAPI)**
- Exposes `/chat` as the orchestration boundary between UI and agent pipeline.
- Handles request normalization, session lookup/update, response validation, and telemetry hooks in one predictable lifecycle.
- Enforces contract stability through Pydantic models so frontend behavior is deterministic even when retrieval/generation paths vary.
- Hosts operational endpoints (`/health`, `/metrics`, `/analytics`) to support debugging and evaluation during rapid iteration.

3. **Intelligence Router**
- Central decision engine that fuses deterministic extraction (regex IDs) with semantic planning (LLM intent + symptom understanding).
- Resolves entities against local truth maps (`part_id_map`, `model_to_parts`) before route selection to prevent downstream hallucinated assumptions.
- Applies scope guardrails (refrigerator/dishwasher only), topic-drift checks, and confidence scoring before invoking expensive retrieval/generation.
- Implements handler-based branching (`part_lookup`, `compatibility`, `symptom_solution`, `model_required`, `clarification_needed`) for clear failure/recovery paths.
- Preserves session continuity but gates carry-forward entities so stale context does not hijack a new user intent.

4. **Retrieval + Generation**
- Uses a dual retrieval strategy: exact JSON/map lookups for correctness-critical fields and vector retrieval for symptom-to-part relevance.
- Performs compatibility-first filtering when model evidence is valid, then reranks candidates using relevance plus practical heuristics.
- Generates grounded responses from retrieved context (not raw user prompt only), then applies post-generation validation before returning output.
- Guarantees schema-safe output via Pydantic contracts, allowing the UI to render rich components without defensive parsing logic.

In practice, this architecture intentionally separates **decisioning** (router) from **knowledge access** (tools/retrieval) and **presentation** (frontend). That separation is what makes the system extensible: adding a new intent generally means adding a handler and retrieval recipe, not rewriting the whole stack.

## Data Strategy
### Structured Store (JSON)
Used for deterministic lookups and compatibility checks:
- `part_id_map.json` → part details,
- `model_id_to_parts_map.json` / `model_to_parts_map.json` → model compatibility lists.

### Semantic Store (Vector DB)
Used for symptom-based retrieval:
- Bedrock Titan embeddings,
- Chroma persistent collection,
- top-k similarity retrieval,
- reranking by symptom overlap, rating, and basic commercial heuristics.

## Query Lifecycle
Each request follows this sequence:
1. **Candidate extraction**
- Run deterministic regex extraction for part/model IDs to capture high-precision identifiers immediately.

2. **Planner analysis**
- Run LLM planner for intent + symptom semantics (install help, compatibility, troubleshooting, or clarification path), with lightweight follow-up shortcuts for common continuation turns.

3. **Entity resolution and validation**
- Cross-check extracted IDs against local maps, tag `part_id_valid` / `model_id_valid`, and preserve only trustworthy session carryover.

4. **Guardrails and scope enforcement**
- Enforce refrigerator/dishwasher scope, detect drift, and block unsupported appliance paths with a constrained clarification response.

5. **Confidence gating**
- Compute a confidence score from extraction quality, validation outcomes, and conversational context to decide whether to proceed, ask for model, or request clarification.

6. **Handler route selection**
- Route to specialized handlers (`part_lookup`, `compatibility`, `symptom`, `model_required`, etc.) so each intent has a purpose-built retrieval + response strategy.

7. **Retrieval and ranking**
- Pull deterministic data from structured maps, optionally augment with vector search, apply compatibility constraints, then rerank candidates for practical usefulness.

8. **Generation and post-validation**
- Generate grounded response content from retrieved context and run post-generation checks before returning schema-validated JSON to the UI.

## Design Decisions
### 1) Hybrid extraction over single-method extraction
- Regex is deterministic for IDs.
- LLM is used for semantic intent/symptom understanding.
- This avoids both LLM-only fragility and regex-only rigidity.

### 2) Monolithic orchestrator over microservices
- Current volume and team size do not justify microservice complexity.
- Keeps debugging and iteration speed high for this stage.

### 3) Compatibility filter before final recommendation quality
- Compatibility mismatch is costlier than semantic mismatch.
- Incompatible parts are filtered early whenever model validation is available.

### 4) Graceful degradation for unknown models
- If model is not in local compatibility data, agent does not over-claim fit.
- It provides clarification and likely alternatives with explicit verification messaging.

### 5) Structured output contract
- All responses use Pydantic models for frontend stability and easier integration.

## Performance and Reliability
### Current behavior
- Deterministic routes (clarification/model-required/out-of-scope) are fast.
- Enriched `part_lookup` answers can be slower due to generation latency.

### Latest local eval snapshot
- Required prompts: **100% pass**
- Edge prompts: **100% pass**
- Required p95 latency: ~**2.65s**
- Edge p95 latency: ~**2.45s**

### Important note for Loom
`part_lookup` tail latency remains the main optimization target.

This is an explicit next-step path (without reducing answer quality):
- keep current quality path,
- optimize generation latency/caching/warm paths for install/part-details responses.

## Frontend UX Highlights
- Search within conversation,
- confidence/status badges,
- structured sections (`Answer`, `Steps`, `Tips`, `Parts`),
- context strip (`Model`, `Appliance`),
- quick actions and recovery prompts,
- export and clear chat controls.

## API Endpoints
- `POST /chat` - primary chat endpoint.
- `GET /health` - service health + state summary.
- `GET /metrics` - lightweight runtime metrics.
- `GET /analytics` - aggregated metrics view.
- `GET /debug/cache-stats` - planner cache stats.

## Setup
### Backend
```bash
cd backend_fastapi
./scripts/setup.sh
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Expected frontend API config:
- `frontend/.env.local`
```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Testing and Validation
### Unit + API tests
```bash
cd backend_fastapi
source .venv/bin/activate
pytest -q tests
```

### Eval harness
```bash
cd backend_fastapi
source .venv/bin/activate
python eval/run_eval.py
```

Generated report:
- `backend_fastapi/reports/eval_report.md`

## Repository Structure
```text
backend_fastapi/
  app/
    agent/          # router, planner, handlers, models, validators
    core/           # config, state, metrics
    tools/          # part lookup + vector search
    main.py         # FastAPI app
  artifacts/        # scraped data + vector artifacts
  eval/             # eval runner
  tests/            # behavior + API tests

frontend/
  app/
    api/chat/route.ts
    components/
    page.tsx
```

## Known Limitations
- Model coverage is bounded by the scraped compatibility dataset.
- Session state is in-memory per process.
- Tail latency for enriched `part_lookup` responses is higher than deterministic routes.

## Next Iteration Priorities
1. Reduce `part_lookup` tail latency while preserving response richness.
2. Expand model compatibility coverage and add data freshness workflow.
3. Add production hardening toggles (CORS allowlist, debug endpoint gating, external session store).
