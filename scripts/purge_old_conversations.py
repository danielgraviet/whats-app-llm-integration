"""List, back up, and delete stale Firestore conversations.

Dry run (default) — lists candidates and writes them to a candidates file:
    python scripts/purge_old_conversations.py --older-than-hours 48

Delete — only the ids in a candidates file produced by a dry run, after a
fresh backup of every document and a re-check that each is still stale:
    python scripts/purge_old_conversations.py --delete --candidates backups/candidates_<ts>.json

"Stale" means Firestore updated_at (last activity of any kind) is older than
the cutoff. Credentials come from the same env files as the dashboard/browser
(--env-file overrides). Nothing is deleted without --delete AND a candidates
file, and every deleted document is saved first under backups/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_env(explicit: str | None):
    files = [Path(explicit)] if explicit else [ROOT / "browser/.env", ROOT / "dashboard/.env", ROOT / f".env.{os.getenv('APP_ENV', 'local')}"]
    loaded = [p for p in files if p.is_file() and (load_dotenv(p, override=False) or True)]
    if not (os.getenv("FIREBASE_CREDS_PATH") or os.getenv("FIREBASE_CREDS_JSON")):
        sys.exit("No Firebase credentials found (looked in: " + ", ".join(map(str, files)) + ")")
    return loaded


def _utc(ts):
    if isinstance(ts, dt.datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
    return None


def jsonable(v):
    if isinstance(v, dt.datetime):
        return _utc(v).isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [jsonable(x) for x in v]
    return v


def mask(phone: str) -> str:
    return phone[:4] + "*" * max(0, len(phone) - 8) + phone[-4:] if len(phone) > 8 else "*" * len(phone)


def summarize(doc_id: str, d: dict) -> dict:
    hist = d.get("history") or []
    ts = [_utc(m.get("timestamp")) for m in hist if _utc(m.get("timestamp"))]
    raw_first = d.get("first_message_raw") or {}
    started = None
    if raw_first.get("timestamp"):
        try: started = dt.datetime.fromtimestamp(int(raw_first["timestamp"]), tz=dt.timezone.utc)
        except (ValueError, TypeError): pass
    started = started or (min(ts) if ts else None)
    pv = d.get("prompt_variant") or ""
    return {
        "id": doc_id,
        "updated_at": jsonable(_utc(d.get("updated_at"))),
        "started_at": jsonable(started),
        "phase": d.get("conversation_phase"),
        "variant": pv.split("_prompt_", 1)[1] if "_prompt_" in pv else pv,
        "turns": int(d.get("user_turn_count") or 0),
        "messages": len(hist),
        "ratings": len(d.get("feeling_array") or []),
        "ad": ((d.get("referrals") or [{}])[0].get("referral") or {}).get("source_id") if d.get("referrals") else None,
        "profile": ((d.get("first_contacts_raw") or [{}])[0].get("profile") or {}).get("name"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--older-than-hours", type=float, default=48)
    ap.add_argument("--env-file")
    ap.add_argument("--delete", action="store_true", help="actually delete (requires --candidates)")
    ap.add_argument("--candidates", help="candidates file from a previous dry run")
    args = ap.parse_args()
    if args.delete and not args.candidates:
        sys.exit("--delete requires --candidates <file from a dry run>")

    load_env(args.env_file)
    from database import firebase
    client = firebase.init_firestore()
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=args.older_than_hours)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    out_dir = ROOT / "backups"; out_dir.mkdir(exist_ok=True)

    docs = {doc.id: (doc.to_dict() or {}) for doc in client.collection("conversations").stream()}
    print(f"{len(docs)} conversations in Firestore; cutoff = updated_at < {cutoff.isoformat()} ({args.older_than_hours:g} h ago)")

    stale = {i: d for i, d in docs.items() if (_utc(d.get("updated_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)) < cutoff}
    rows = sorted((summarize(i, d) for i, d in stale.items()), key=lambda r: r["updated_at"] or "")

    if not args.delete:
        cand = out_dir / f"candidates_{stamp}.json"
        cand.write_text(json.dumps({"generated_at": now.isoformat(), "cutoff": cutoff.isoformat(), "older_than_hours": args.older_than_hours, "candidates": rows}, indent=2))
        print(f"\n{len(rows)} candidate(s) for deletion (full list with ids: {cand.relative_to(ROOT)})\n")
        print(f"{'id (masked)':16} {'last activity (UTC)':20} {'started (UTC)':20} {'phase':24} {'var':4} {'turns':5} {'msgs':4} {'rat':3} {'ad':6} profile")
        for r in rows:
            print(f"{mask(r['id']):16} {(r['updated_at'] or '')[:19]:20} {(r['started_at'] or '')[:19]:20} {str(r['phase']):24} {str(r['variant'])[:1]:4} "
                  f"{r['turns']:5} {r['messages']:4} {r['ratings']:3} {str(r['ad'] or '-'):6} {r['profile'] or ''}")
        keep = len(docs) - len(rows)
        print(f"\n{keep} conversation(s) would be KEPT (activity within the last {args.older_than_hours:g} h).")
        return

    # ---- delete path ----
    cand = json.loads(Path(args.candidates).read_text())
    ids = [r["id"] for r in cand["candidates"]]
    print(f"candidates file lists {len(ids)} id(s), generated {cand['generated_at']}")
    missing = [i for i in ids if i not in docs]
    fresh = [i for i in ids if i in docs and i not in stale]
    to_delete = [i for i in ids if i in stale]
    if missing: print(f"  {len(missing)} already gone, skipping")
    if fresh: print(f"  {len(fresh)} became active since the dry run, KEEPING: {', '.join(mask(i) for i in fresh)}")
    if not to_delete:
        print("nothing to delete"); return

    backup = out_dir / f"conversations_backup_{stamp}.json"
    backup.write_text(json.dumps({"backed_up_at": now.isoformat(), "documents": {i: jsonable(docs[i]) for i in to_delete}}, indent=2, ensure_ascii=False))
    print(f"backed up {len(to_delete)} document(s) to {backup.relative_to(ROOT)} ({backup.stat().st_size:,} bytes)")

    coll = client.collection("conversations")
    done = 0
    for k in range(0, len(to_delete), 400):
        batch = client.batch()
        for i in to_delete[k:k + 400]:
            batch.delete(coll.document(i))
        batch.commit()
        done += len(to_delete[k:k + 400])
    remaining = sum(1 for _ in coll.stream())
    print(f"deleted {done} conversation(s); {remaining} remain in Firestore")


if __name__ == "__main__":
    main()
