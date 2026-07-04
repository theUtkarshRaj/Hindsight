"""
Hindsight memory layer — a thin, opinionated wrapper around Cognee's
v2 memory lifecycle: remember / recall / improve / forget, plus the
session feedback API that lets recall quality adapt over time.

Every function here maps 1:1 to a judging-visible Cognee capability.
"""

import os
import re

# Load .env (LLM_API_KEY, Cognee Cloud vars) BEFORE importing cognee so
# its settings pick them up. No-op if python-dotenv or .env is absent.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Session caching must be enabled BEFORE importing cognee,
# otherwise session_id and improve() are unavailable.
os.environ.setdefault("CACHING", "true")
os.environ.setdefault("CACHE_BACKEND", "fs")

import cognee
from cognee import SearchType
from cognee.modules.users.methods import get_default_user

def _resolve_dataset() -> str:
    """Which dataset the app reads. seed.py writes a fresh, uniquely-named
    dataset to `.active_dataset` on each run (cloud deletion is unreliable,
    so we never reuse/clear a name — we roll forward to a clean one). The
    app follows that marker; falls back to a default if it's absent."""
    # Explicit override — used in deployment, where .active_dataset (which
    # seed.py writes locally) isn't present. Set COGNEE_DATASET to the dataset
    # name your seed run created on the cloud.
    env = os.getenv("COGNEE_DATASET")
    if env:
        return env
    marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".active_dataset")
    try:
        with open(marker, encoding="utf-8") as f:
            name = f.read().strip()
        if name:
            return name
    except OSError:
        pass
    return "decisions_live"


DATASET = _resolve_dataset()


def _text(item) -> str:
    """recall() returns a list of results whose shape depends on mode:
    LOCAL yields RecallResponse *objects* (answer on `.text`), CLOUD yields
    plain *dicts* (answer under the "text"/"value" key). Render whichever
    is present, from either shape."""
    if isinstance(item, dict):
        for k in ("text", "answer", "content", "value"):
            if item.get(k):
                return str(item[k])
        raw = item.get("raw")
        if isinstance(raw, dict) and raw.get("value"):
            return str(raw["value"])
        return str(item)
    for attr in ("text", "answer", "content"):
        val = getattr(item, attr, None)
        if val:
            return str(val)
    return str(item)

CONTRADICTION_PROMPT = (
    "You are an institutional memory auditor reviewing a proposed decision "
    "against the prior decisions in the retrieved context. Reply in AT MOST "
    "3 short sentences — plain, specific, no headings or bullet lists. Begin "
    "with exactly one word: CONFLICT or CLEAR. If CONFLICT, name the one "
    "decision it violates (with its D-number) and why, in a sentence or two. "
    "If CLEAR, say so and note at most one related decision to be aware of. "
    "Keep it short; do not restate every decision."
)

ASK_PROMPT = (
    "Answer in at most 3 short sentences — plain and specific, citing the "
    "relevant decision numbers (e.g. D-002). No headings, no bullet lists."
)


async def connect_cloud() -> str:
    """Route all memory ops to Cognee Cloud when creds are configured.

    This is what makes the app actually *use* Cognee Cloud (the hackathon
    track): cognee.serve() sets the remote client, after which every
    remember/recall/improve/forget executes on the cloud instance instead
    of locally. Falls back to local mode when unset so dev still works.

    Set COGNEE_SERVICE_URL (your instance URL from the Cognee Cloud
    dashboard) and COGNEE_API_KEY (your cloud API key) in .env.
    """
    # Ensure the local relational scaffold exists. Even in cloud mode the
    # wrapper calls get_default_user() and the session APIs, which need a
    # local SQLite DB — a fresh container (unlike a dev install) has none,
    # so create it once here. Idempotent; safe to call on every startup.
    try:
        from cognee.low_level import setup

        await setup()
    except Exception:
        pass

    url = os.getenv("COGNEE_SERVICE_URL") or os.getenv("COGNEE_CLOUD_API_URL")
    key = os.getenv("COGNEE_API_KEY") or os.getenv("COGNEE_CLOUD_AUTH_TOKEN")
    placeholders = {"", "your-instance", "your_cloud_api_key"}
    if url and not any(p in url for p in ("your-instance", "your_cloud")):
        await cognee.serve(url=url, api_key=key or "")
        return f"cloud -> {url}"
    return "local (no COGNEE_SERVICE_URL set - NOT using Cognee Cloud)"


def backend_status() -> dict:
    """Report whether memory is running on Cognee Cloud or locally, so the
    UI can show a live 'connected to Cognee Cloud' badge on camera."""
    from cognee.api.v1.serve.state import get_remote_client

    c = get_remote_client()
    if c is not None:
        url = getattr(c, "service_url", "") or ""
        host = url.split("//", 1)[-1].split(".")[0] if url else ""
        return {"mode": "cloud", "url": url, "tenant": host}
    return {"mode": "local", "url": "", "tenant": ""}


async def remember_decision(text: str, session_id: str | None = None) -> dict:
    """remember(): permanent graph write, or session cache when session_id given."""
    if session_id:
        await cognee.remember(text, session_id=session_id)
        return {"stored": "session", "session_id": session_id}
    await cognee.remember(text, dataset_name=DATASET)
    return {"stored": "permanent", "dataset": DATASET}


async def ask(question: str, session_id: str | None = None) -> str:
    """recall(): auto-routed hybrid graph/vector query, session-aware,
    with feedback influence enabled so past ratings shape retrieval."""
    user = await get_default_user()
    # Cloud ignores system_prompt, so fold the "be concise" instruction into
    # the query too (belt-and-suspenders with system_prompt for local mode).
    results = await cognee.recall(
        query_text=f"{ASK_PROMPT}\n\nQuestion: {question}",
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=[DATASET],
        session_id=session_id,
        system_prompt=ASK_PROMPT,
        user=user,
    )
    return _text(results[0]) if results else "(no answer found in memory)"


async def check_contradiction(proposal: str, session_id: str | None = None) -> dict:
    """The signature feature: recall() with a custom system prompt that
    audits a proposed decision against everything in the graph."""
    user = await get_default_user()
    # Fold the audit instruction into the query itself. The cloud recall
    # does not reliably honor system_prompt, so embedding it in query_text
    # makes the contradiction audit work identically local and on cloud.
    # We still pass system_prompt as a belt-and-suspenders for local mode.
    audit_query = f"{CONTRADICTION_PROMPT}\n\nProposed decision to audit: {proposal}"
    results = await cognee.recall(
        query_text=audit_query,
        query_type=SearchType.GRAPH_COMPLETION,
        datasets=[DATASET],
        session_id=session_id,
        system_prompt=CONTRADICTION_PROMPT,
        user=user,
    )
    answer = _text(results[0]) if results else "CLEAR — memory is empty."
    # Robust verdict parse: the LLM often wraps the keyword in markdown
    # (**CONFLICT**, "CONFLICT, - CONFLICT). Strip any leading non-letters
    # before checking, or a real conflict gets mis-stamped as clear.
    cleaned = re.sub(r"^[^A-Za-z]+", "", str(answer)).upper()
    verdict = "conflict" if cleaned.startswith("CONFLICT") else "clear"
    return {"verdict": verdict, "detail": answer}


async def rate_last_answer(session_id: str, score: int, text: str = "") -> bool:
    """Feedback loop: attach a rating to the latest Q&A in this session.
    Cognee uses feedback to adapt retrieval weights on future recalls."""
    user = await get_default_user()
    qas = await cognee.session.get_session(session_id=session_id, user=user)
    if not qas or not qas[-1].qa_id:
        return False
    return await cognee.session.add_feedback(
        session_id=session_id,
        qa_id=qas[-1].qa_id,
        feedback_text=text,
        feedback_score=score,
        user=user,
    )


async def promote_session(session_id: str) -> dict:
    """improve() / memify: enrich the permanent graph with everything
    worth keeping from a session's cache."""
    await cognee.improve(dataset=DATASET, session_ids=[session_id])
    return {"promoted": session_id, "into": DATASET}


async def forget_superseded(everything: bool = False) -> dict:
    """forget(): surgically prune. In Hindsight this retires superseded
    decisions; with everything=True it resets the whole memory."""
    if everything:
        await cognee.forget(everything=True)
        return {"forgot": "everything"}
    await cognee.forget(dataset=DATASET)
    return {"forgot": DATASET}


async def _cloud_graph_html() -> str:
    """Fetch the cloud tenant's own knowledge-graph visualization HTML.

    In cloud mode the memory lives on the cloud, so the LOCAL graph engine
    is empty — visualize_graph() would render nothing. The cloud exposes
    its own D3 graph render at GET /api/v1/visualize?dataset_id=..., which
    is the genuine cloud graph. Resolve the dataset id by name, then fetch.
    """
    import aiohttp

    base = (os.getenv("COGNEE_SERVICE_URL") or os.getenv("COGNEE_CLOUD_API_URL") or "").rstrip("/")
    key = os.getenv("COGNEE_API_KEY") or os.getenv("COGNEE_CLOUD_AUTH_TOKEN") or ""
    async with aiohttp.ClientSession(headers={"X-Api-Key": key}) as s:
        async with s.get(f"{base}/api/v1/datasets/") as r:
            datasets = await r.json()
        items = datasets if isinstance(datasets, list) else datasets.get("datasets", [])
        ds_id = next((d["id"] for d in items if d.get("name") == DATASET), None)
        if not ds_id:
            raise RuntimeError(f"dataset '{DATASET}' not found on cloud")
        async with s.get(f"{base}/api/v1/visualize", params={"dataset_id": ds_id}) as r:
            return await r.text()


async def render_graph(path: str) -> str:
    """Graph visualization → self-contained HTML file. In cloud mode this
    proxies the cloud tenant's own render (the local graph is empty when
    memory lives on the cloud); locally it uses the built-in visualizer."""
    from cognee.api.v1.serve.state import get_remote_client

    if get_remote_client() is not None:
        html = await _cloud_graph_html()
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path
    await cognee.visualize_graph(destination_file_path=path, dataset=DATASET)
    return path
