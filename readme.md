# Instalily Case Study: PartSelect AI Support Agent

## Overview
This project implements an AI support agent for PartSelect focused on **refrigerator** and **dishwasher** parts. Beyond the core workflows, additional edge and follow-up conversation paths are covered in the automated tests under `backend_fastapi/tests`.

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
![Archtecture Diagram](<API LAYER (FastAPI)  (1).png>)


1. **Frontend (Next.js chat UI)** - Renders intent-specific UI blocks (answers, install steps, compatibility, troubleshooting, parts) and maintains lightweight context chips for smooth multi-turn support. Uses optimistic interactions (quick actions, loading, retry/export) while keeping all business logic in the backend.

2. **API Layer (FastAPI)** - Exposes /chat as the orchestration boundary handling normalization, session state, validation, and telemetry in a single predictable lifecycle. Enforces contract stability with Pydantic models so frontend behavior stays deterministic even as retrieval or generation paths vary.

3. **Intelligence Router**
- Central decision engine combining regex-based ID extraction with LLM intent understanding, preserving session continuity while preventing stale context from overriding new intent.
- Validates entities against local truth maps before routing, applies scope guardrails and confidence checks, and branches into clear handler paths (part_lookup, compatibility, symptom_solution, etc.) for reliable recovery.

4. **Retrieval + Generation**
- Uses dual retrieval: exact JSON/map lookups for correctness-critical data and vector search for symptom relevance, with compatibility-first filtering and heuristic reranking.
- Generates grounded responses from retrieved context, validates post-generation, and enforces schema-safe output via Pydantic so the UI can render without defensive parsing.

We separate decisioning (router), knowledge access (retrieval/tools), and presentation (frontend) to keep responsibilities modular and clear.
This keeps the system extensible, new intents mean adding a handler and retrieval logic, not rebuilding the stack.


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
1. **Candidate extraction** - Run deterministic regex extraction for part/model IDs to capture high-precision identifiers immediately.

2. **Planner analysis** - Run LLM planner for intent + symptom semantics (install help, compatibility, troubleshooting, or clarification path), with lightweight follow-up shortcuts for common continuation turns.

3. **Entity resolution and validation** - Cross-check extracted IDs against local maps, tag `part_id_valid` / `model_id_valid`, and preserve only trustworthy session carryover.

4. **Guardrails and scope enforcement** - Enforce refrigerator/dishwasher scope, detect drift, and block unsupported appliance paths with a constrained clarification response.

5. **Confidence gating** - Compute a confidence score from extraction quality, validation outcomes, and conversational context to decide whether to proceed, ask for model, or request clarification.

6. **Handler route selection** - Route to specialized handlers (`part_lookup`, `compatibility`, `symptom`, `model_required`, etc.) so each intent has a purpose-built retrieval + response strategy.

7. **Retrieval and ranking** - Pull deterministic data from structured maps, optionally augment with vector search, apply compatibility constraints, then rerank candidates for practical usefulness.

8. **Generation and post-validation** - Generate grounded response content from retrieved context and run post-generation checks before returning schema-validated JSON to the UI.

## Design Decisions & System Philosophy
This is not just an LLM wrapper over product data. It is a constrained support system that uses deterministic logic for correctness-critical decisions and probabilistic reasoning only where semantics are required.

### Core principles
- **Deterministic when possible** - Uses regex for high-precision ID extraction and resolves part/model truth from local maps rather than generated text, with guardrails and routing constraints enforced before invoking expensive generation.
- **Probabilistic when necessary** - LLM planner handles intent classification and symptom semantics. Semantic retrieval handles natural-language troubleshooting that exact matching cannot.
- **Validate before and after AI** - Enforces safeguards both before and after AI invocation: pre-AI entity validation and scope checks, followed by post-AI output validation with strict schema contracts.
- **Confidence-aware routing** - Confidence score controls whether to proceed, ask for model, or clarify. Low-confidence turns degrade safely instead of forcing brittle guesses.
- **Hard constraints > soft similarity** - Compatibility constraints are applied before final recommendation paths when model evidence is valid Similarity helps ranking, but does not override compatibility.

### Key architecture decisions
1. **Hybrid extraction over single-method extraction**
- Regex is deterministic for IDs. LLM is used for semantic intent/symptom understanding.
- This avoids both LLM-only fragility and regex-only rigidity.

2. **Monolithic orchestrator over microservices**
- Current volume of requests do not justify microservice complexity.
- Keeps debugging and iteration speed high for this stage.

3. **Compatibility filter before final recommendation quality**
- Compatibility mismatch is costlier than semantic mismatch.
- Incompatible parts are filtered early whenever model validation is available.

4. **Graceful degradation for unknown models**
- If model is not in local compatibility data, agent does not over-claim fit.
- It provides clarification and likely alternatives with explicit verification messaging.

### Confidence Formula (Implemented)
The router uses a weighted score and thresholds to drive route selection:

```text
confidence = 0.10 * part_regex_match + 0.10 * model_regex_match + 0.15 * part_id_valid
  + 0.15 * model_id_valid + 0.08 * model_present_but_unvalidated + 0.40 * llm_planner_confidence 
  + 0.05 * session_model_plus_symptom + 0.05 * session_has_last_symptom
```

This gives measurable uncertainty handling instead of binary pass/fail routing. Current threshold behavior:
- `< 0.55`: clarification/model-required style recovery paths.
- `>= 0.55`: intent-specific handlers execute.

### Hallucination Prevention
Hallucination prevention is layered:
- **Grounding before generation** - Part IDs and model IDs are validated against local maps. Unknown models are marked unvalidated and handled explicitly.
- **Scope and topic controls** - Enforces scope guardrails and topic-drift checks to block unsupported appliances and prevent stale context from affecting new queries.
- **Post-generation checks** - Validates generated part IDs against the catalog, applies intent-specific quality checks, and enforces Pydantic response contracts to prevent malformed frontend payloads.

### Cost-Aware Design
Cost and latency controls are built into architecture choices:

| Mechanism | What it saves | Trade-off |
|---|---|---|
| Deterministic-first routing | Fewer LLM calls on clear turns. | More routing logic to maintain. |
| Planner caching | Lower repeat latency and token cost. | Small memory overhead. |
| Follow-up shortcuts | Faster continuation turns. | Requires conservative trigger rules. |
| Fast deterministic response types | Cheap, responsive low-context handling. | Less rich answers until context arrives. |
| Monolithic deployment | Lower infra and ops cost. | Fewer independent scaling knobs. |

### Semantic Search Strategy
Troubleshooting retrieval combines recall and precision:
- Bedrock Titan embeddings + Chroma persistent index for semantic recall.
- Compatibility-aware filtering when model evidence is valid.
- Reranking combines semantic relevance with practical heuristics.
- Final answer is generated from retrieved context and validated before return.

### Production Reliability: Fallbacks, Guardrails, Graceful Degradation
These mechanisms are treated as product reliability features, not optional AI behavior:
- **Fallback mechanisms & Graceful degradation** - Low-confidence or weak validation paths shift to clarification or constrained guidance instead of guessing, ensuring users always receive an actionable next step with explicit uncertainty.
- **Guardrails** - Strict appliance scope, entity validation, and topic-drift checks prevent invalid IDs, unsafe domain drift, and cross-turn context bleed.

## Performance and Reliability
### Current behavior

- Deterministic routes (clarification/model-required/out-of-scope) are fast.
- Enriched `part_lookup` answers can be slower due to generation latency.

### Latest local eval snapshot

| Metric | Result |
|---|---|
| Required prompts pass rate | **100%** |
| Edge prompts pass rate | **100%** |
| Required p95 latency | ~**1.65s** |
| Edge p95 latency | ~**1.45s** |

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
