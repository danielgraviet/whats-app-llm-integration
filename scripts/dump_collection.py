"""Back up a Firestore collection to a JSON Lines file, one document per line.

    python scripts/dump_collection.py --key ~/Downloads/<service-account>.json \
        --collection web_conversations --out backups/web_conversations_phase1.jsonl

Every field is kept; Firestore timestamps become ISO-8601 strings, so the file
is plain JSON that any tool can read (pandas: pd.read_json(path, lines=True)).
The document id is stored under "_id". Subcollections are not followed (the
study documents have none).

The key argument accepts a service-account JSON file, a file holding its
base64 form, or a `FIREBASE_CREDS_JSON=...` line, like scripts/migrate_firestore.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_firestore import client_for  # noqa: E402


def jsonable(v):
    if isinstance(v, dt.datetime):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True)
    ap.add_argument("--collection", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    client = client_for(args.key)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for snap in client.collection(args.collection).stream():
            row = {"_id": snap.id, **jsonable(snap.to_dict() or {})}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    print(f"{client.project}/{args.collection}: {n} documents -> {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
