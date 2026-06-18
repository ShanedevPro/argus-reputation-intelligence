import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_engine_agent_files_compile():
    for relative_path in [
        "QueryEngine/agent.py",
        "MediaEngine/agent.py",
        "InsightEngine/agent.py",
    ]:
        py_compile.compile(str(ROOT / relative_path), doraise=True)
