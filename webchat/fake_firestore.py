"""Minimal in-memory stand-in for the Firestore client, for --demo and tests.

Supports exactly what database/firebase.py uses: collection().document(),
get/set(merge)/update/delete, ArrayUnion merging, stream(), where() on a
single field, and a no-op transaction. Data lives in a dict and is lost on
restart. Never use this for real participants.
"""

from __future__ import annotations

import datetime as dt

from google.cloud import firestore as _fs


class _Doc:
    def __init__(self, id, data): self.id, self._d = id, data
    @property
    def exists(self): return self._d is not None
    def to_dict(self): return dict(self._d) if self._d is not None else None


class _DocRef:
    def __init__(self, store, id): self._s, self.id = store, id
    def get(self, transaction=None): return _Doc(self.id, self._s.get(self.id))
    def set(self, data, merge=False):
        cur = dict(self._s.get(self.id) or {}) if merge else {}
        for k, v in data.items():
            if isinstance(v, _fs.ArrayUnion):
                lst = list(cur.get(k, []))
                for item in v.values:
                    if item not in lst: lst.append(item)
                cur[k] = lst
            else:
                cur[k] = v
        self._s[self.id] = cur
    def update(self, data):
        if self.id not in self._s: raise KeyError(f"no document {self.id}")
        self.set(data, merge=True)
    def delete(self): self._s.pop(self.id, None)


class _Query:
    def __init__(self, store, flt=None): self._s, self._f = store, flt
    def where(self, filter=None, **kw):
        return _Query(self._s, filter)
    def stream(self):
        for id, d in list(self._s.items()):
            if self._f is not None:
                v = d.get(self._f.field_path)
                if v is None or not (v > self._f.value): continue
            yield _Doc(id, d)
    def document(self, id): return _DocRef(self._s, id)


class _Txn:
    def update(self, ref, data): ref.update(data)


class FakeFirestore:
    def __init__(self): self._collections: dict[str, dict] = {}
    def collection(self, name): return _Query(self._collections.setdefault(name, {}))
    def transaction(self): return _Txn()
    def batch(self):
        ops = []
        class B:
            def delete(self_, ref): ops.append(ref)
            def commit(self_):
                for r in ops: r.delete()
        return B()


def install_transactional_shim():
    """firebase.get_and_clear_pending_response wraps its body in
    @firestore.transactional, which needs a real Transaction. In fake mode we
    replace the decorator with identity BEFORE database.firebase is imported."""
    _fs.transactional = lambda fn: fn
