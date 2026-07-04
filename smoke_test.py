"""
Import-level smoke test — verifies the app wiring loads and the fixed
signatures line up with the installed Cognee, WITHOUT needing LLM/Cloud
keys or a database. Run inside the venv:

    .venv/Scripts/python.exe smoke_test.py

A green run here means the three bug fixes are structurally sound; it
does NOT exercise remember/recall/feedback end-to-end (those need keys).
"""

import inspect
import sys


def check(cond, msg):
    mark = "OK  " if cond else "FAIL"
    print(f"[{mark}] {msg}")
    return cond


def main() -> int:
    ok = True

    import cognee
    print(f"cognee version: {getattr(cognee, '__version__', '?')}")
    print(f"cognee module:  {cognee.__file__}\n")

    # v2 lifecycle API is present under the names the app uses
    for name in ("remember", "recall", "improve", "forget", "visualize_graph"):
        ok &= check(hasattr(cognee, name), f"cognee.{name} exists")
    ok &= check(hasattr(cognee, "session"), "cognee.session exists")
    for name in ("get_session", "add_feedback"):
        ok &= check(hasattr(cognee.session, name), f"cognee.session.{name} exists")

    # add_feedback really takes (session_id, qa_id, ...) — the bug we fixed
    sig = inspect.signature(cognee.session.add_feedback)
    params = list(sig.parameters)
    ok &= check(params[:2] == ["session_id", "qa_id"],
                f"add_feedback first two params are (session_id, qa_id) -> got {params[:2]}")

    # QA entries expose .qa_id (not .id)
    from cognee.infrastructure.databases.cache.models import SessionQAEntry
    fields = SessionQAEntry.model_fields
    ok &= check("qa_id" in fields, "SessionQAEntry has qa_id field")
    ok &= check("id" not in fields, "SessionQAEntry has NO id field (must use qa_id)")

    # Our wrapper imports cleanly and the helper renders objects to text
    import memory
    ok &= check(callable(memory._text), "memory._text helper present")

    class _Graph:  # mimics a graph-completion RecallResponse
        text = "CONFLICT with D-002"
    class _QA:
        answer = "session answer"
    ok &= check(memory._text(_Graph()) == "CONFLICT with D-002",
                "_text extracts .text from graph result")
    ok &= check(memory._text(_QA()) == "session answer",
                "_text falls back to .answer")

    print()
    print("ALL GREEN — wiring + fixed signatures verified." if ok
          else "SOME CHECKS FAILED — see [FAIL] lines above.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
