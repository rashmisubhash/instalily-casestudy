# Frontend Architecture: PartSelect Chat UI (Next.js)

## Scope and Role
The frontend is a typed interaction layer over the backend response contract. It prioritizes:
- fast user input loops
- readable, actionable response rendering
- resilient multi-turn context UX
- graceful handling of backend/network errors

It does **not** own business decisioning (intent routing, compatibility truth, retrieval policy). That remains in the backend.

## Runtime Topology
```text
User input (browser)
  -> useChatLogic state machine
  -> POST /api/chat (Next route handler)
  -> FastAPI /chat
  -> structured response payload
  -> Message renderer (typed UI sections)
  -> context strip / quick actions / recovery prompts
```

## Component Architecture
### 1) Screen composition (`app/page.tsx`)
`ChatPage` is the UI orchestrator.

Responsibilities:
- compose top-level layout (`Header`, chat card, input area)
- select data from hook (`messages`, `filteredMessages`, `isLoading`, etc.)
- derive context strip state (`activeModel`, `activeAppliance`)
- render recovery bar when error-shaped assistant messages are detected
- connect per-message quick actions back to input setter

Key design choice:
- display logic is centralized in page composition; data mutation stays in `useChatLogic`.

### 2) Interaction state machine (`app/components/chat/useChatLogic.ts`)
`useChatLogic` is the client-side controller.

State owned:
- `messages`
- `input`
- `isLoading`
- `searchQuery`
- `conversationId`

Lifecycle behavior:
1. on mount: restore or create `conversationId` (`localStorage`)
2. on mount: restore chat history (`localStorage`)
3. on state change: persist messages
4. on message/loading update: auto-scroll to latest

Submit flow (`handleSubmit`):
1. guard (`input.trim`, `!isLoading`, `conversationId`)
2. append user message immediately (optimistic local update)
3. send `/api/chat` request with timeout (`AbortController`, 30s)
4. update `conversationId` if backend returns canonical ID
5. append assistant message from structured payload (`explanation` or `message`)
6. on failure: retry (max 2 for non-timeout), then render user-safe error copy

Utility behaviors:
- keyboard shortcuts: `Ctrl/Cmd+Enter` submit, `Esc` clear input
- clear chat: reset state + new conversation ID
- export chat: serialize transcript to downloadable `.txt`
- search: in-memory message filtering by content

### 3) Message rendering pipeline (`app/components/chat/Message.tsx`)
`Message.tsx` maps backend payload fields to explicit UI blocks.

Render model:
- user role: plain bubble
- assistant role: structured card sections with optional blocks

Assistant rendering blocks:
- confidence badge from numeric score (`getConfidenceLabel`)
- model tag when `payload.model_id` exists
- markdown answer body (with newline normalization)
- ordered steps (`diagnostic_steps`)
- `recommended_parts` and `alternative_parts` via `ProductCard`
- `part` detail card for lookup paths
- `helpful_tips` list
- intent-aware "Next Actions" button grid

Why this matters:
- each backend response type can be rendered deterministically from known fields
- avoids dumping raw JSON or relying on brittle template strings

### 4) Request proxy boundary (`app/api/chat/route.ts`)
The Next route handler isolates browser from backend URL/cors concerns.

Behavior:
- validates `message` presence (`400` on missing input)
- forwards request to `${NEXT_PUBLIC_API_URL}/chat`
- passes through backend JSON on success
- normalizes backend failure bodies into a stable `500` response shape

This gives a single frontend-controlled integration point for backend failures.

## Response-Type Rendering Matrix
Current UI behavior by backend response shape:

| Backend type | Primary UI blocks | UX goal |
|---|---|---|
| `part_lookup` | answer + part card + related/next actions | installation and part detail guidance |
| `compatibility` | compatibility explanation + part card + alternatives (if any) | fit/no-fit decision support |
| `symptom_solution` | answer + diagnostic steps + recommended parts + tips | troubleshooting progression |
| `model_required` / `issue_required` | clarification text + next actions | collect missing context efficiently |
| `clarification_needed` | constrained guidance + follow-up prompts | safe recovery from uncertainty/out-of-scope |

## Context, Continuity, and Recovery UX
### Context strip
Derived from latest known evidence:
- model from explicit payload (`model_id`) or detected model in user message
- appliance from payload fields/symptom hints

### Recovery mechanisms
- loading feedback (`TypingIndicator`, `LoadingSkeleton`)
- recovery bar appears for failure-copy patterns
- one-click recovery prompts feed directly into input state
- quick actions available in welcome and message contexts

## Persistence Model
Local browser persistence keys:
- `partselect-conversation-id`
- `partselect-chat-history`

Trade-off:
- improves continuity on refresh
- does not provide cross-device sync

## Error Semantics and Resilience
Frontend error classes and behavior:
- timeout (`AbortError`) -> "Request timed out"
- transport failure (`Failed to fetch`) -> "Cannot connect to the server"
- non-OK backend -> structured server error message

Retry policy:
- automatic retries for transient non-timeout errors (up to 2)
- then user-facing fallback response in chat thread

## Styling and Presentation Contract
Styling is class-driven (see `styles/globals.css`) with semantic UI tokens for:
- message roles and entry animations
- confidence badge variants
- section headers and cards
- quick action grids and recovery bars

Presentation principle:
- style reflects response certainty and task progression, not just cosmetics.

## Runtime Configuration
Required env var in `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Local Development
```bash
cd frontend
npm install
npm run dev
```

Production build validation:
```bash
npm run build
```

## File-Level Map
```text
app/
  page.tsx                         # top-level orchestration/composition
  layout.tsx                       # app shell
  api/chat/route.ts                # backend proxy
  components/
    layout/Header.tsx
    chat/
      useChatLogic.ts              # state machine + side effects
      Message.tsx                  # payload -> UI renderer
      ProductCard.tsx              # part card primitive
      ChatInput.tsx                # composer + controls
      SearchBar.tsx                # in-thread search
      QuickActions.tsx             # one-click prompt starters
      WelcomeScreen.tsx            # first-run onboarding state
      TypingIndicator.tsx          # loading affordance
      LoadingSkeleton.tsx          # loading placeholder
```

## Known Constraints
- browser-local persistence only
- runtime rendering depends on backend schema stability
- UX responsiveness tracks backend tail latency on generation-heavy routes

## Extension Playbook
To support a new backend response type safely:
1. add render branch and UI block mapping in `Message.tsx`
2. add suggested next actions for that type
3. add fallback behavior for partial/missing fields
4. add/update style classes in `styles/globals.css`
5. verify end-to-end with `/api/chat` integration and loading/error states
