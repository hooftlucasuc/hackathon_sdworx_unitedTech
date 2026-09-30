# CallSight — dashboard (role C)

An SD Worx consultant leads the call; CallSight listens in and shows, during the call, who is calling, what to ask next and which solution fits best. Contract change for live listening: [`../docs/contract-live.md`](../docs/contract-live.md).

Vite + React + TypeScript. Reads live from Firestore (`onSnapshot`, read-only) and writes through B's API.

## Getting started

```bash
npm install
cp .env.example .env.local
npm run dev
```

Opens on http://localhost:5173 (= `FRONTEND_ORIGIN` in the backend CORS).

## Two modes

| `VITE_DATA_SOURCE` | What |
|---|---|
| `mock` (default) | Dummy data in the browser following the contract, including the score formula. The demo menu plays a live call. No backend needed. |
| `firestore` | Live from Firestore (`calls`, `callers`, `companies`, `solutions`). "It worked / It didn't work" → `POST /calls/{id}/resolve`, demo menu → `POST /demo/simulate-call`. |

With `VITE_DEMO_MODE=true` the top bar has a **Demo call ▾** menu with the three demo scenarios (returning caller, new colleague at a known company, unknown problem). Each one plays a call of about 25 seconds live: the transcript streams in, caller and problem are recognised, follow-up questions appear and the suggestions get sharper. With demo data this happens in the browser; live, the menu sends `POST /demo/simulate-call` and B plays it. For a demo with a real call, set it to `false`.

## Plan B on demo day

If Firestore or the backend drops out, there is nothing to restart:

- If the dashboard gets no data after 8 seconds or cannot connect, a message appears with the button **Switch to demo data**.
- Or add `?source=demo` to the URL yourself: http://localhost:5173/?source=demo. **back to live** next to "● Demo data", or `?source=live`, takes you back.

Demo data lives only in the browser: reloading resets it.

If one part of the screen fails (e.g. because of unexpected data), only that part shows a message with **Try again**; the rest keeps working.

## What the screen shows

One calm screen for the consultant, who reads out what CallSight suggests. Styled after sdworx.be: white base, light grey surfaces, SD Worx Display for headings, a blue band with a slanted bottom edge.

- **Blue band at the top:** who is calling and from which company, "3rd call" or "First call", urgency, category, and during the call "● Live" with a timer.
- **Conversation** (top): this call so far, like a chat, with the newest words at the bottom while people talk (`partial`). After the call, the summary appears underneath.
- **Bottom, "Ask now"** (during a live call): the question to ask now, large enough to read out, with the reason and, for each possible answer, the follow-up question. While the caller talks, the dashboard recognises the answer (`src/answers.ts`), ticks it off and puts the follow-up on top; an answer can also be clicked.
- **Bottom, "Offer this solution" / "Consult this document"**: appears by itself when nothing is left to ask or the call ends, or earlier via "Offer the best solution now". Shows the best solution with match label and score, its chance of success ("93% success · worked 13 of 14 times"), the document to consult (source, title, section, link), the text to read out, "It worked" / "It didn't work", and **Why not the others?** with what the other candidates are for. Below the threshold: "No strong match: escalate to an expert".
- **Best matches** (side): the top candidates with source and chance of success, updating live. Click one to offer it.
- **Calls** (button top right): drawer with recent calls to open an earlier one. By default the screen follows the latest call.
- **Demo call** (button top right, only with `VITE_DEMO_MODE=true`): four demo scenarios, including **Which document?**, where three documents fit and the follow-up questions narrow it down to one.

The contract stores categories, urgencies and sources as Dutch values (`vakantiegeld`, `hoog`, `handboek`, …); the dashboard shows English labels (`CATEGORY_LABEL`, `URGENCY_LABEL`, `SOURCE_LABEL` in `src/types.ts`). Solution texts and suggested questions are shown as B and D store them. `solutions.document` (`{title, section?, url?}`) is a proposed addition, see `docs/contract-live.md`.

## What the dashboard expects from the other roles

- **B:** `calls.started_at` as a Firestore Timestamp (used for sorting). The score is 0–100, the `reasons` 0–1. CORS open for `http://localhost:5173`.
- **B/D:** Firestore rules that allow the dashboard to read. The rules in `infra/firestore.rules` only let team members with the `agent` claim read, so the dashboard still needs a Google sign-in (open task for C, see `TEAMPLAN.md` §6).

## Structure

```
src/
  types.ts              contract (collections, labels, score weights, escalation threshold)
  answers.ts            recognises expected answers while the caller talks
  data/firestore.ts     live reading from Firestore
  data/mock.ts          dummy data + score formula for working offline
  data/demoPayloads.ts  the 3 scenarios as a scripted live call (and webhook body)
  data/hooks.ts         React hooks on top of the chosen data source
  api.ts                resolve + simulate-call
  components/           CallView, CallerBanner, Conversation, NextQuestions, Solutions, CallList, DemoMenu
```
