"""
Hindsight API — FastAPI backend wiring the UI to Cognee.

Run:  uvicorn app:app --reload --port 8080
Then open http://localhost:8080
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

import memory


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect to Cognee Cloud (if creds are set) BEFORE serving requests,
    # so every memory op runs on the cloud instance.
    mode = await memory.connect_cloud()
    print(f"[hindsight] memory backend: {mode}", flush=True)
    yield


app = FastAPI(
    title="Hindsight — institutional memory that talks back",
    lifespan=lifespan,
)

STATIC = Path(__file__).parent / "static"
GRAPH_HTML = Path(__file__).parent / "graph_snapshot.html"


class RememberBody(BaseModel):
    text: str
    session_id: str | None = None


class AskBody(BaseModel):
    question: str
    session_id: str | None = None


class ProposalBody(BaseModel):
    proposal: str
    session_id: str | None = None


class FeedbackBody(BaseModel):
    session_id: str
    score: int
    text: str = ""


class SessionBody(BaseModel):
    session_id: str


class ForgetBody(BaseModel):
    everything: bool = False


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/status")
async def api_status():
    return memory.backend_status()


@app.post("/api/remember")
async def api_remember(body: RememberBody):
    return await memory.remember_decision(body.text, body.session_id)


@app.post("/api/ask")
async def api_ask(body: AskBody):
    answer = await memory.ask(body.question, body.session_id)
    return {"answer": answer}


@app.post("/api/propose")
async def api_propose(body: ProposalBody):
    return await memory.check_contradiction(body.proposal, body.session_id)


@app.post("/api/feedback")
async def api_feedback(body: FeedbackBody):
    ok = await memory.rate_last_answer(body.session_id, body.score, body.text)
    return {"ok": ok}


@app.post("/api/promote")
async def api_promote(body: SessionBody):
    return await memory.promote_session(body.session_id)


@app.post("/api/forget")
async def api_forget(body: ForgetBody):
    return await memory.forget_superseded(body.everything)


@app.get("/api/graph")
async def api_graph():
    path = await memory.render_graph(str(GRAPH_HTML))
    return FileResponse(path, media_type="text/html")
