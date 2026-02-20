# Backend Architecture: PartSelect Support Agent (FastAPI)

## Scope and Role
The backend is the policy and orchestration layer for the assistant. It turns user text into validated, structured actions for PartSelect refrigerator and dishwasher support flows.

Primary supported intents:
- part installation and lookup
- compatibility check
- symptom troubleshooting
- clarification/model-required recovery paths

## Runtime Architecture
```text
FastAPI /chat
  -> session load + conversation summary
  -> ApplianceAgent.handle_query (router)
      -> deterministic extraction (regex)
      -> planner (LLM intent/entities)
      -> validation + guardrails
      -> confidence scoring
      -> handler dispatch
          -> retrieval (JSON maps + vector search)
          -> response generation
          -> post-validation
  -> structured response + metrics
```

## Component Breakdown
### 1) API boundary (`app/main.py`)
Responsibilities:
- FastAPI app lifecycle + middleware
- `POST /chat` orchestration boundary
- in-memory `sessions` store keyed by `conversation_id`
- response wrapping (`ChatResponse`) and error translation
- operational endpoints: `/health`, `/metrics`, `/analytics`, `/debug/cache-stats`

Important details:
- sessions store entity memory + last messages (trimmed window)
- conversation summary is built from recent turns and passed to router/planner context
- app-level metrics and structured logs are emitted per request

### 2) Router / policy engine (`app/agent/router.py`)
`ApplianceAgent` is the control plane. It decides *what should happen next*.

Core pipeline in `handle_query(...)`:
1. low-signal query guard (`_is_low_signal_query`) -> immediate clarification route
2. deterministic candidate extraction (`extract_candidates`) for part/model IDs
3. planner + prefetch in parallel (`ThreadPoolExecutor`):
   - `_prefetch_part(...)`, `_prefetch_model(...)`
   - `planner.plan(...)` (or `_build_followup_symptom_plan(...)` for deterministic follow-up shortcut)
4. entity resolution (`validate_and_resolve`) with DB-backed validity flags
5. scope guardrail (`check_scope`) + topic drift guardrail (`check_topic_drift`)
6. confidence scoring (`compute_confidence`)
7. session merge (`merge_state`)
8. route dispatch (`route`)

Routing behavior highlights:
- priority route: valid part + install/lookup intent -> `handle_part_lookup`
- low confidence with symptom and no model -> `handle_model_required`
- compatibility with unvalidated model -> `handle_compatibility_unvalidated`
- symptom with unvalidated model -> `handle_symptom_troubleshoot_unvalidated`
- unknown/low-signal -> `handle_clarification_needed`

### 3) Planner (`app/agent/planner.py`)
`ClaudePlanner` provides intent/entity parsing from natural language.

Implementation details:
- Bedrock invocation (`anthropic.claude-3-haiku-20240307-v1:0` by default)
- strict JSON-only response prompt
- normalization/validation of parsed fields in `_validate_plan(...)`
- in-memory cache (`_cache`, max 1000 entries)
- deterministic settings for classification (`temperature=0.0`)
- fallback plan on planner failure (`_fallback_plan`)

### 4) Handlers (`app/agent/handlers.py`)
Handlers implement intent-specific execution semantics.

Key handlers:
- `handle_part_lookup(...)`
  - reads part from map
  - generates install response
  - validates response structure
  - returns part + related parts + steps/tips
- `handle_compatibility(...)`
  - deterministic compatibility check (`check_compatibility`)
  - returns compatible true/false with explanation
  - for incompatible cases, returns compatible alternatives
- `handle_compatibility_unvalidated(...)`
  - explicit non-verified compatibility response
  - vector-backed likely alternatives + clarification prompts
- `handle_symptom_troubleshoot(...)`
  - vector retrieval + model filter + rerank
  - grounded diagnostic generation and confidence refinement
- `handle_symptom_troubleshoot_unvalidated(...)`
  - graceful degradation path when model is unknown
  - broad search fallback + popular parts fallback
- `handle_model_required(...)`, `handle_issue_required(...)`, `handle_clarification_needed(...)`
  - recovery scaffolding with explicit next-step prompts

### 5) Retrieval and tooling (`app/tools/part_tools.py`)
Retrieval stack combines deterministic and semantic methods:
- deterministic lookups from `state["part_id_map"]`
- deterministic compatibility checks from `state["model_id_to_parts_map"]`
- semantic retrieval via:
  - Bedrock Titan embeddings (`amazon.titan-embed-text-v1`)
  - Chroma persistent collection
- parsed vector documents are enriched with map metadata where available

### 6) Validators (`app/agent/validators.py`)
Safety and quality checks:
- block hallucinated part IDs not present in catalog map
- intent-specific checks (e.g., part lookup steps bounds, symptom mention checks)
- shared scope/topic utility methods for validation

## Data Layer and State Model
### Source-of-truth state (`app/core/state.py`)
Global in-memory maps loaded at startup:
- `part_id_map`: part_id -> part metadata
- `model_id_to_parts_map`: model_id -> compatible part IDs

State characteristics:
- JSON-backed, memory-resident for low-latency lookups
- auto-load on import, with reload utility for development

### Why this model
- deterministic correctness for compatibility-sensitive operations
- no network dependency for critical path lookups
- explicit bounded scope for case-study dataset

Scraper/data pipeline in brief:
- Offline scraping generates normalized JSON artifacts in `artifacts/scrape/data/` (parts map + model compatibility map).
- A vector build step indexes the same dataset into Chroma so semantic retrieval remains consistent with deterministic maps.

## Confidence Model and Route Gating
Confidence is computed in `compute_confidence(...)` as weighted evidence:

```text
confidence =
  +0.10 (regex part hit)
  +0.10 (regex model hit)
  +0.15 (part validated in map)
  +0.15 (model validated in map)
  +0.08 (model present but unvalidated)
  +0.40 * planner_confidence
  +0.05 (session has model and current symptom)
  +0.05 (session has last_symptom)
```

Threshold behavior:
- `< 0.55`: recovery paths (clarification/model-required or constrained fallback)
- `>= 0.55`: normal intent handler execution

This gives uncertainty-aware behavior instead of binary pass/fail routing.

## Retrieval and Ranking Details
### Symptom retrieval path
1. build search query from symptom + optional appliance/brand context
2. deduplicate repeated terms (`_build_search_query`)
3. vector search (`top_k`)
4. if model validated: hard compatibility filter (`_filter_by_model`)
5. rerank (`_rerank_results`) using:
   - base similarity score
   - symptom keyword overlap boost
   - rating/popularity boost
   - high-price penalty
6. pass top candidates to diagnostic generation

### Rerank scoring shape
`final_score = similarity + symptom_boost + popularity_boost + price_penalty`

This keeps compatibility as hard constraint while using semantic signals for ranking quality.

## Guardrails, Fallbacks, and Degradation
### Guardrails
- appliance scope boundary (refrigerator/dishwasher)
- keyword-based out-of-scope secondary filter
- topic drift reset across appliance switches
- entity validation before compatibility/recommendation claims

### Fallback/degradation strategy
- low-signal user input -> constrained clarification template
- unvalidated model in compatibility flow -> explicit uncertainty + likely alternatives
- symptom path search failures -> broad query fallback -> popular parts fallback
- planner or generation failures -> safe fallback responses

Design goal: never dead-end; always return an actionable next step.

## API Contract Surface
Primary endpoint:
- `POST /chat`

Operational endpoints:
- `GET /health`
- `GET /metrics`
- `GET /analytics`
- `GET /debug/cache-stats`

Debug/session endpoints:
- `GET /session/{conversation_id}`
- `DELETE /session/{conversation_id}`

## File-Level Map
```text
app/
  main.py                  # API boundary, sessions, endpoint wiring
  agent/
    router.py              # orchestration + policy + route gating
    planner.py             # LLM intent/entity planner + cache
    handlers.py            # intent execution logic
    validators.py          # post-gen and safety checks
    models.py              # response schemas (Pydantic)
  tools/
    part_tools.py          # lookup, compatibility, vector search
  core/
    state.py               # in-memory data maps
    metrics.py             # metrics logging/aggregation
    config.py              # env/config values
```

## Local Runbook
```bash
cd backend_fastapi
./scripts/setup.sh
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Bedrock auth/env notes:
- If your local auth flow uses bearer tokens, export `AWS_BEARER_TOKEN_BEDROCK`.
- Otherwise `boto3` resolves standard AWS credentials/profile (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`).

## Testing and Evaluation
Test suites:
- `tests/test_chat_api.py`
- `tests/test_router_behavior.py`
- `tests/test_compatibility_unvalidated.py`
- `tests/test_symptom_troubleshoot.py`

Run:
```bash
cd backend_fastapi
source .venv/bin/activate
pytest -q tests
python eval/run_eval.py
```

Eval report output:
- `reports/eval_report.md`

## Known Constraints
- session storage is in-memory (single-process)
- compatibility coverage is bounded by scraped dataset
- `part_lookup` tail latency remains the main latency hotspot

## Extension Playbook
To add a new intent:
1. extend planner intent schema/prompt behavior
2. add handler implementation in `handlers.py`
3. add route policy branch in `router.py`
4. update/extend `AgentResponse` model fields if required
5. add tests for happy path + low-confidence + out-of-scope cases
