"""Ordering guard in brownout.edge.set_level, checked against an in-memory stand-in for KeyValueStore.

Run: uv run python tests/test_edge_ordering.py   (no AWS access needed)
"""
import os, sys, types
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
os.environ.update(BROWNOUT_BUCKET="b", BROWNOUT_KVS_ARN="arn")
import brownout.edge as edge

class Conflict(Exception): pass
class NotFound(Exception): pass
class FakeKVS:
    exceptions = types.SimpleNamespace(ConflictException=Conflict, ResourceNotFoundException=NotFound)
    def __init__(s): s.data={}; s.etag=0; s.interfere=0
    def describe_key_value_store(s, KvsARN): return {"ETag": str(s.etag)}
    def get_key(s, KvsARN, Key):
        if Key not in s.data: raise NotFound()
        return {"Value": s.data[Key]}
    def update_keys(s, KvsARN, IfMatch, Puts):
        if s.interfere: s.interfere-=1; s.etag+=1; raise Conflict()
        if IfMatch!=str(s.etag): raise Conflict()
        for p in Puts: s.data[p["Key"]]=p["Value"]
        s.etag+=1
fake=FakeKVS()
edge.boto3=types.SimpleNamespace(client=lambda *a, **k: fake)
T4,T5="2026-11-10T12:00:00Z","2026-11-10T12:00:05Z"
assert edge.set_level(5, T5) is True                 # newer alert lands first
assert edge.is_stale(T4) is True                     # older one is recognised as stale
assert edge.set_level(4, T4) is False and fake.data["level"]=="5"   # and cannot roll back
assert edge.set_level(5, T5) is True                 # a retry of the same alert is harmless
fake.interfere=2
assert edge.set_level(1, "2026-11-10T12:01:00Z") is True and fake.data["level"]=="1"  # survives concurrent writes
assert edge.set_level(3) is True and fake.data["level"]=="3"   # manual switch without a timestamp still works
assert edge.is_stale(None) is False
print("all ordering checks passed")
