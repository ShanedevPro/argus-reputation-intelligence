"""Report Engine package metadata and lazy public exports."""

from importlib import import_module

__version__ = "1.0.0"
__author__ = "Report Engine Team"

__all__ = ["ReportAgent", "create_agent"]


def __getattr__(name):
    if name in __all__:
        agent_module = import_module(".agent", __name__)
        return getattr(agent_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
