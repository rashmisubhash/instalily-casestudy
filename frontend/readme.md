# Frontend Architecture: PartSelect Chat UI (Next.js)

## What This App Owns
The frontend is a structured support interface over a strict backend response contract. It focuses on clarity, recoverability, and multi-turn usability rather than embedding business logic in the UI.

## Core Responsibilities
- Collect user input and maintain conversation flow
- Render assistant payloads into actionable UI sections
- Preserve local conversation continuity (history + conversation ID)
- Provide search, export, retry, and recovery interactions
- Proxy requests through Next API route to backend service

## High-Level Architecture
### 1) Page composition (`app/page.tsx`)
Top-level screen orchestration:
- Header and layout shell
- Search bar and filtered message view
- Context strip (`Model`, `Appliance`) derived from latest evidence
- Quick actions bar and recovery actions
- Input area and loading states

### 2) State and behavior hook (`app/components/chat/useChatLogic.ts`)
Central client-side state machine:
- message list and filtered views
- input and loading state
- conversation ID generation/restoration
- localStorage persistence for history/session continuity
- submit/retry/timeout/error handling
- clear/export utilities

### 3) Message rendering system (`app/components/chat/Message.tsx`)
Transforms backend payload into structured UI blocks:
- confidence badges
- answer markdown
- diagnostic/install steps
- recommended/alternative parts cards
- helpful tips
- intent-aware next-action buttons

### 4) Backend proxy route (`app/api/chat/route.ts`)
Server-side bridge from browser to FastAPI backend:
- validates basic input (`message` required)
- forwards request to `${NEXT_PUBLIC_API_URL}/chat`
- normalizes backend/API failures into frontend-safe error responses

## UI Component Map
- `Header.tsx`: top app frame
- `WelcomeScreen.tsx`: initial guidance/examples
- `QuickActions.tsx`: one-click prompts
- `SearchBar.tsx`: in-chat filtering
- `ChatInput.tsx`: composer + submit/export/clear controls
- `TypingIndicator.tsx` / `LoadingSkeleton.tsx`: loading feedback
- `ProductCard.tsx`: part display card
- `MessageFeedback.tsx`: response feedback UI

## Data Contract with Backend
Frontend expects structured response payloads from `/chat` and renders by type and fields.
Common fields used in UI:
- `type`
- `confidence`
- `explanation` or `message`
- `model_id`
- `diagnostic_steps`
- `recommended_parts` / `alternative_parts`
- `helpful_tips`

UI strategy: render known fields explicitly; fallback to safe text display for partial payloads.

## Conversation and Context Handling
- `conversation_id` is persisted in localStorage and reused across turns
- chat history is persisted locally and restored on reload
- detected model/context chips are derived from payload first, then message heuristics
- recovery bar appears when backend/network error copy is detected

## Error Handling and Resilience
- Request timeout via `AbortController` (30s)
- Automatic retry (up to 2 attempts for non-timeout failures)
- User-facing failure copy for timeout and connectivity issues
- Backend proxy returns structured error payloads for UI fallback display

## Runtime Configuration
Required env var (`frontend/.env.local`):

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Local Development
```bash
cd frontend
npm install
npm run dev
```

Production build check:
```bash
npm run build
```

## Frontend Directory Layout
```text
app/
  page.tsx
  layout.tsx
  api/chat/route.ts
  components/
    layout/Header.tsx
    chat/
      useChatLogic.ts
      Message.tsx
      ProductCard.tsx
      ChatInput.tsx
      SearchBar.tsx
      QuickActions.tsx
      WelcomeScreen.tsx
      TypingIndicator.tsx
      LoadingSkeleton.tsx
```

## Known Constraints
- LocalStorage persistence is browser-local (not shared across devices)
- Message rendering assumes backend schema stability
- UX quality depends on backend response quality and latency

## Extending the Frontend
To add a new backend response type:
1. Add payload rendering branch in `Message.tsx`
2. Add next-action hints if applicable
3. Update style tokens/classes in `styles/globals.css`
4. Add a hook-level fallback path for missing fields
