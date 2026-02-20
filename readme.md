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
![Archtecture Diagram](<API LAYER (FastAPI)  (1).png>)

The system is organized into four layers:

1. **Frontend (Next.js chat UI)** - Renders intent-specific UI blocks (answers, install steps, compatibility, troubleshooting, parts) and maintains lightweight context chips for smooth multi-turn support. Uses optimistic interactions (quick actions, loading, retry/export) while keeping all business logic in the backend.

2. **API Layer (FastAPI)** - Exposes /chat as the orchestration boundary handling normalization, session state, validation, and telemetry in a single predictable lifecycle. Enforces contract stability with Pydantic models so frontend behavior stays deterministic even as retrieval or generation paths vary.

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
- **Deterministic when possible**
  - Regex extraction handles high-precision IDs.
  - Part/model truth is resolved from local maps, not generated text.
  - Guardrails and route constraints execute before expensive generation.
- **Probabilistic when necessary**
  - LLM planner handles intent classification and symptom semantics.
  - Semantic retrieval handles natural-language troubleshooting that exact matching cannot.
- **Validate before and after AI**
  - Pre-AI: entity validation and scope enforcement.
  - Post-AI: output validators and strict schema contracts.
- **Confidence-aware routing**
  - Confidence score controls whether to proceed, ask for model, or clarify.
  - Low-confidence turns degrade safely instead of forcing brittle guesses.
- **Hard constraints > soft similarity**
  - Compatibility constraints are applied before final recommendation paths when model evidence is valid.
  - Similarity helps ranking, but does not override compatibility.

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

5. **Structured output contract**
- All responses use Pydantic models for frontend stability and easier integration.

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
- **Grounding before generation**
  - Part IDs and model IDs are validated against local maps.
  - Unknown models are marked unvalidated and handled explicitly.
- **Scope and topic controls**
  - Out-of-scope appliances are blocked with constrained responses.
  - Topic-drift checks reduce stale context contamination.
- **Post-generation checks**
  - Generated part IDs are checked against the known catalog.
  - Intent-specific validators enforce response quality constraints.
  - Pydantic response contracts prevent malformed frontend payloads.

### Cost-Aware Design
Cost and latency controls are built into architecture choices:
- Deterministic extraction and map lookups run before LLM-heavy paths.
- Planner responses are cached for repeated user patterns.
- Follow-up symptom turns use deterministic shortcuts where safe.
- Fast deterministic routes avoid unnecessary long generation calls.
- Monolithic orchestration keeps infra overhead low at this scale.

### Semantic Search Strategy
Troubleshooting retrieval combines recall and precision:
- Bedrock Titan embeddings + Chroma persistent index for semantic recall.
- Compatibility-aware filtering when model evidence is valid.
- Reranking combines semantic relevance with practical heuristics.
- Final answer is generated from retrieved context and validated before return.

### Production Reliability: Fallbacks, Guardrails, Graceful Degradation
These mechanisms are treated as product reliability features, not optional AI behavior:
- **Fallback mechanisms**
  - If confidence is low, the system falls back to clarification or model-required paths instead of guessing.
  - If model validation fails, compatibility flow shifts to constrained guidance (explicit uncertainty + alternatives), not hard failure.
  - If retrieval quality is weak, router selects safe response types with clear next-step prompts.
- **Guardrails**
  - Strict appliance scope boundary (refrigerator/dishwasher) limits unsafe domain drift.
  - Entity validation guardrails prevent invalid part/model IDs from entering recommendation logic.
  - Topic drift checks reduce cross-turn context bleed when user intent changes.
- **Graceful degradation**
  - Responses degrade from "definitive answer" to "guided clarification" while preserving user momentum.
  - The user always receives an actionable next step (provide model, confirm part, clarify symptom), not a dead-end error.
  - Degradation paths keep trust by being explicit about uncertainty instead of presenting overconfident output.

## Performance and Reliability
### Current behavior
- Deterministic routes (clarification/model-required/out-of-scope) are fast.
- Enriched `part_lookup` answers can be slower due to generation latency.

### Latest local eval snapshot
- Required prompts: **100% pass**
- Edge prompts: **100% pass**
- Required p95 latency: ~**1.65s**
- Edge p95 latency: ~**1.45s**

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
