"""
Seed Hindsight's permanent memory with realistic decision records.

Run once before the demo:  python seed.py
"""

import asyncio
import os
import uuid

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

os.environ.setdefault("CACHING", "true")
os.environ.setdefault("CACHE_BACKEND", "fs")

import cognee

from memory import connect_cloud

# Mint a fresh, unique dataset each seed run and record it so the app follows
# it. Cloud deletion is unreliable, so instead of clearing an old dataset we
# always roll forward to a clean one — the "learn live" demo beat needs a
# baseline with no ad-hoc decisions left over from a previous take.
DATASET = f"decisions_{uuid.uuid4().hex[:8]}"
_MARKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".active_dataset")

DECISIONS = [
    # A connected web of decisions — the graph edges are the demo.
    "Decision D-001 (2025-03-12, owner: Priya, status: active): We will use "
    "PostgreSQL as the primary datastore. Rationale: the team already runs "
    "Postgres in production for billing, and hiring for it is easy. "
    "Alternatives considered: MongoDB, DynamoDB.",

    "Decision D-002 (2025-04-02, owner: Marco, status: active): All customer "
    "PII must stay in the EU region. Rationale: two enterprise customers "
    "require GDPR data residency in their contracts. This constrains every "
    "future infrastructure decision.",

    "Decision D-003 (2025-05-20, owner: Priya, status: active): We standardize "
    "on Python 3.12 for backend services. Rationale: dependency compatibility "
    "with our ML pipeline; D-001's Postgres drivers are well supported.",

    "Decision D-004 (2025-07-08, owner: Ana, status: superseded by D-007): "
    "Deploy on a single us-east-1 AWS region to keep costs low during beta.",

    "Decision D-007 (2025-11-15, owner: Ana, status: active): Migrate all "
    "workloads to eu-central-1. Rationale: D-004 conflicted with the PII "
    "residency requirement in D-002 once the first EU enterprise customer "
    "signed. Supersedes D-004.",

    "Decision D-009 (2026-01-30, owner: Marco, status: active): No third-party "
    "analytics SDKs in the mobile app. Rationale: every SDK we audited ships "
    "device identifiers to US servers, which violates D-002.",
]


async def _remember_with_retry(text: str, attempts: int = 4) -> bool:
    """Cloud remember() can transiently 409 (e.g. right after a forget while
    the dataset deletion settles). Retry with backoff and keep going rather
    than crashing the whole seed on one record."""
    for i in range(1, attempts + 1):
        try:
            await cognee.remember(text, dataset_name=DATASET)
            return True
        except Exception as e:
            msg = str(e)[:120]
            if i == attempts:
                print(f"  FAILED after {attempts} tries: {msg}")
                return False
            wait = 4 * i
            print(f"  retry {i}/{attempts - 1} in {wait}s ({msg})")
            await asyncio.sleep(wait)
    return False


async def main():
    print(f"Memory backend: {await connect_cloud()}")
    print(f"Seeding fresh dataset: {DATASET}")
    ok = 0
    for d in DECISIONS:
        if await _remember_with_retry(d):
            ok += 1
            print(f"  remembered: {d[:60]}…")
        # small gap so the cloud pipeline isn't hammered back-to-back
        await asyncio.sleep(2)
    if ok:
        with open(_MARKER, "w", encoding="utf-8") as f:
            f.write(DATASET)
        print(f"\nActive dataset written to .active_dataset -> {DATASET}")
    print(f"Done. Seeded {ok}/{len(DECISIONS)}. Restart the app so it picks up the new dataset:")
    print("  uvicorn app:app --port 8080")


if __name__ == "__main__":
    asyncio.run(main())
