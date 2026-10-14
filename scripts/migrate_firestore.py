"""Copy collections from one Firestore project to another, document by document.

Written for the 2026-10-13 move from the free-plan project `whatsapp-llm-test`
to `urnas-study-2026`. Google's managed export/import needs billing on the
source project, which the free plan does not have, so this reads every
document with the source key and writes it with the destination key.

Dry run (default): counts documents on both sides, writes nothing.
    python scripts/migrate_firestore.py --source-key old.json --dest-key new.json

Copy:
    python scripts/migrate_firestore.py --source-key old.json --dest-key new.json --execute

Each key argument may be a service-account JSON file, a file holding the base64
form, or a file holding a `FIREBASE_CREDS_JSON=...` line as used in .env files.
Documents that already exist in the destination are skipped (ids are random
session ids or phone numbers, so a clash means the same record), unless
--overwrite is given. Subcollections are copied recursively. Field values,
including Firestore timestamps, are copied as they are. Safe to rerun.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

from google.cloud import firestore
from google.oauth2 import service_account

BATCH = 400  # Firestore allows 500 writes per batch


def load_key(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8").strip()
    if raw.startswith("{"):
        return json.loads(raw)
    if "=" in raw.split("\n", 1)[0] and raw.upper().startswith("FIREBASE_CREDS_JSON="):
        raw = raw.split("=", 1)[1].strip()
    raw = raw.strip("\"'")
    return json.loads(base64.b64decode(raw))


def client_for(path: str) -> firestore.Client:
    info = load_key(path)
    creds = service_account.Credentials.from_service_account_info(info)
    return firestore.Client(project=info["project_id"], credentials=creds)


def copy_collection(src: firestore.CollectionReference, dst: firestore.CollectionReference,
                    execute: bool, overwrite: bool, stats: dict, depth: int = 0) -> None:
    existing = set() if overwrite else {d.id for d in dst.list_documents()}
    batch, pending = (dst._client.batch() if execute else None), 0
    for snap in src.stream():
        stats["source"] += 1
        if snap.id in existing:
            stats["skipped"] += 1
        else:
            stats["to_copy"] += 1
            if execute:
                batch.set(dst.document(snap.id), snap.to_dict())
                pending += 1
                if pending >= BATCH:
                    batch.commit(); stats["written"] += pending
                    batch, pending = dst._client.batch(), 0
        for sub in snap.reference.collections():   # subcollections, if any
            copy_collection(sub, dst.document(snap.id).collection(sub.id), execute, overwrite, stats, depth + 1)
    if execute and pending:
        batch.commit(); stats["written"] += pending


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-key", required=True)
    ap.add_argument("--dest-key", required=True)
    ap.add_argument("--collections", nargs="+", default=["web_conversations", "conversations"])
    ap.add_argument("--execute", action="store_true", help="actually write; default is a dry run")
    ap.add_argument("--overwrite", action="store_true", help="replace documents that already exist in the destination")
    args = ap.parse_args()

    src, dst = client_for(args.source_key), client_for(args.dest_key)
    if src.project == dst.project:
        sys.exit(f"source and destination are the same project ({src.project}); refusing")
    print(f"{'COPY' if args.execute else 'DRY RUN'}: {src.project} -> {dst.project}")

    for name in args.collections:
        stats = {"source": 0, "skipped": 0, "to_copy": 0, "written": 0}
        copy_collection(src.collection(name), dst.collection(name), args.execute, args.overwrite, stats)
        print(f"  {name:20s} source={stats['source']:5d}  already in dest={stats['skipped']:5d}  "
              f"{'written' if args.execute else 'would write'}={stats['written'] if args.execute else stats['to_copy']:5d}")
    if not args.execute:
        print("nothing written (add --execute to copy)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
