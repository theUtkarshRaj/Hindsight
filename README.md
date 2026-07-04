# Hindsight

**Institutional memory that talks back.** Teams make hundreds of decisions, then forget them — and six months later someone confidently proposes the exact thing that was rejected, or quietly contradicts a compliance constraint nobody remembers. Hindsight is an agent that remembers every decision your team has ever made, and *audits every new proposal against all of them* using Cognee's hybrid graph-vector memory.

Built for **The Hangover Part AI** hackathon — Cognee Cloud track.

## The one-sentence demo

> You type "let's add Firebase Analytics to the mobile app" and Hindsight stamps it **⚠ CONFLICT ON RECORD** — because eight months ago the team decided all PII stays in the EU, and it traversed the graph to connect those two facts.

That connection (proposal → analytics SDK → device identifiers → US servers → GDPR decision D-002) is a multi-hop *graph* traversal. A plain vector store finds similar text; Cognee finds the chain of consequences.

## How it uses the full Cognee memory lifecycle

| Operation | Where it lives in Hindsight |
|---|---|
| `remember()` | **Record** mode writes decisions permanently to the graph; conversation turns go to session cache via `session_id` |
| `recall()` | **Ask** mode (graph-routed Q&A) and **Propose** mode (contradiction audit via a custom `system_prompt`) |
| `improve()` / memify | The **improve()** button promotes today's session discussion into permanent institutional memory |
| `forget()` | Retires superseded decisions — memory that prunes itself, not just grows |
| session feedback | Every answer has *useful / off-base* buttons wired to `cognee.session.add_feedback`, so retrieval quality adapts with use |

## Quick start

```bash
pip install cognee fastapi uvicorn

cp .env.example .env      # add your keys (see below)
python seed.py            # load six realistic, interlinked decision records
uvicorn app:app --port 8080
# open http://localhost:8080
```

### Cognee Cloud (hackathon track requirement)

Set your Cloud connection in `.env`:

```
COGNEE_CLOUD_API_URL=<your cloud instance url>
COGNEE_CLOUD_AUTH_TOKEN=<your cloud api key>
LLM_API_KEY=<your llm provider key>
CACHING=true
CACHE_BACKEND=fs
```

Sign up for Cognee Cloud and redeem code `COGNEE-35` for the free Developer plan. Check the Cognee Cloud docs for your instance URL — configuration may vary by plan.

## Demo flow (3 minutes)

1. **Ask** — "Why are we on eu-central-1?" → recall() traverses D-007 → D-002 → D-004 and explains the migration *and its cause*.
2. **Propose** — "Switch primary datastore to MongoDB" → **⚠ CONFLICT** stamp citing D-001 and its rationale.
3. **Propose** — "Add Firebase Analytics" → conflict via the multi-hop GDPR chain. The wow moment.
4. **View graph** — live Cognee `visualize_graph` render, watch the web of decisions.
5. Click **useful** on a good answer → feedback stored, retrieval adapts.
6. **improve()** — promote the session; re-open the graph and see new nodes.
7. Restart the server, ask again — *it still remembers.* No hangover.

## Architecture

```
static/index.html ── fetch ──► app.py (FastAPI) ──► memory.py ──► Cognee Cloud
                                                     │  remember / recall /
                                                     │  improve / forget /
                                                     │  session feedback /
                                                     └─ visualize_graph
```

Three files of application code. The memory layer *is* the product — exactly as the judges intend.
