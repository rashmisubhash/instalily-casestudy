import sys
from pathlib import Path
from types import ModuleType


# Ensure `app` package resolves from backend_fastapi/
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# Provide a lightweight chromadb stub for tests when chromadb isn't installed.
# This keeps production imports strict while letting unit/API tests run in minimal envs.
if "chromadb" not in sys.modules:
    chromadb_stub = ModuleType("chromadb")

    class _FakeCollection:
        def query(self, *args, **kwargs):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def get_collection(self, *args, **kwargs):
            return _FakeCollection()

    chromadb_stub.PersistentClient = _FakeClient
    sys.modules["chromadb"] = chromadb_stub
