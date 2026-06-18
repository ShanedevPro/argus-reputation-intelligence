import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _load_db_module(monkeypatch):
    fake_pkg = types.ModuleType("InsightEngine")
    fake_pkg.__path__ = []
    fake_utils = types.ModuleType("InsightEngine.utils")
    fake_utils.__path__ = []
    fake_config = types.ModuleType("InsightEngine.utils.config")
    fake_config.settings = SimpleNamespace(
        DB_DIALECT="mysql",
        DB_HOST="localhost",
        DB_PORT="3306",
        DB_USER="user",
        DB_PASSWORD="password",
        DB_NAME="media",
    )
    monkeypatch.setitem(sys.modules, "InsightEngine", fake_pkg)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils", fake_utils)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.config", fake_config)

    fake_sqlalchemy = types.ModuleType("sqlalchemy")
    fake_sqlalchemy.text = lambda query: query
    fake_sqlalchemy_ext = types.ModuleType("sqlalchemy.ext")
    fake_sqlalchemy_asyncio = types.ModuleType("sqlalchemy.ext.asyncio")
    fake_sqlalchemy_asyncio.AsyncEngine = object
    fake_sqlalchemy_asyncio.AsyncSession = object
    fake_sqlalchemy_asyncio.create_async_engine = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "sqlalchemy", fake_sqlalchemy)
    monkeypatch.setitem(sys.modules, "sqlalchemy.ext", fake_sqlalchemy_ext)
    monkeypatch.setitem(sys.modules, "sqlalchemy.ext.asyncio", fake_sqlalchemy_asyncio)

    spec = importlib.util.spec_from_file_location(
        "InsightEngine.utils.db",
        ROOT / "InsightEngine" / "utils" / "db.py",
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "InsightEngine.utils.db", module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeResult:
    def mappings(self):
        return self

    def all(self):
        return [{"ok": True}]


class _FakeConnection:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append(("execute", str(statement), params))
        return _FakeResult()

    async def exec_driver_sql(self, query, params):
        self.calls.append(("exec_driver_sql", query, params))
        return _FakeResult()


class _FakeConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return _FakeConnectionContext(self.connection)


def test_fetch_all_uses_driver_sql_for_positional_params(monkeypatch):
    db = _load_db_module(monkeypatch)

    connection = _FakeConnection()
    monkeypatch.setattr(db, "get_async_engine", lambda: _FakeEngine(connection))

    rows = asyncio.run(db.fetch_all("SELECT * FROM `weibo_note` WHERE `content` LIKE %s", ("%小米SU7%",)))

    assert rows == [{"ok": True}]
    assert connection.calls == [
        ("exec_driver_sql", "SELECT * FROM `weibo_note` WHERE `content` LIKE %s", ("%小米SU7%",))
    ]


def test_fetch_all_uses_text_execute_for_named_params(monkeypatch):
    db = _load_db_module(monkeypatch)

    connection = _FakeConnection()
    monkeypatch.setattr(db, "get_async_engine", lambda: _FakeEngine(connection))

    rows = asyncio.run(db.fetch_all("SELECT * FROM weibo_note WHERE content LIKE :term", {"term": "%小米SU7%"}))

    assert rows == [{"ok": True}]
    assert connection.calls == [
        ("execute", "SELECT * FROM weibo_note WHERE content LIKE :term", {"term": "%小米SU7%"})
    ]
