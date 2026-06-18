#!/usr/bin/env python3
"""Preflight checks for the local Argus demo."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Iterable

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - reported as an import check below
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if load_dotenv is not None:
        env_file = os.environ.get("ARGUS_ENV_FILE")
        if env_file:
            load_dotenv(Path(env_file), override=False)
        load_dotenv(ROOT / ".env", override=False)

    failures: list[str] = []

    require_env("TIKHUB_API_KEY", failures)
    require_env("POSTGRES_URL", failures)
    require_chat_model_config(failures)
    require_engine_family("INSIGHT_ENGINE", failures)
    require_engine_family("MEDIA_ENGINE", failures)
    require_engine_family("QUERY_ENGINE", failures)
    require_engine_family("REPORT_ENGINE", failures)
    require_search_provider_config(failures)
    require_env("TAVILY_API_KEY", failures, label="TAVILY_API_KEY for QueryEngine")

    for module_name, package_name in [
        ("dotenv", "python-dotenv"),
        ("flask", "Flask"),
        ("tavily", "tavily-python"),
        ("sqlalchemy", "SQLAlchemy"),
        ("tikhub", "tikhub"),
    ]:
        require_import(module_name, package_name, failures)

    if failures:
        print("\nPreflight failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("\nPreflight passed: required local demo config and imports are available.")
    return 0


def require_env(name: str, failures: list[str], label: str | None = None) -> None:
    if env_value(name):
        print(f"OK {label or name}: SET")
        return
    print(f"MISSING {label or name}")
    failures.append(f"{label or name} is required")


def require_first_available(
    names: Iterable[str], failures: list[str], label: str
) -> None:
    if any(env_value(name) for name in names):
        print(f"OK {label}: SET")
        return
    printable_names = " / ".join(names)
    print(f"MISSING {label}: {printable_names}")
    failures.append(f"{label} is required via one of: {printable_names}")


def require_chat_model_config(failures: list[str]) -> None:
    require_first_available(
        [
            "ARGUS_CHAT_BASE_URL",
            "QUERY_ENGINE_BASE_URL",
            "REPORT_ENGINE_BASE_URL",
            "INSIGHT_ENGINE_BASE_URL",
            "MEDIA_ENGINE_BASE_URL",
        ],
        failures,
        "Argus chat base URL",
    )
    require_first_available(
        [
            "ARGUS_CHAT_API_KEY",
            "QUERY_ENGINE_API_KEY",
            "REPORT_ENGINE_API_KEY",
            "INSIGHT_ENGINE_API_KEY",
            "MEDIA_ENGINE_API_KEY",
        ],
        failures,
        "Argus chat API key",
    )
    require_first_available(
        ["ARGUS_CHAT_MODEL", "QUERY_ENGINE_MODEL_NAME"],
        failures,
        "Argus chat model",
    )


def require_engine_family(prefix: str, failures: list[str]) -> None:
    require_env(f"{prefix}_BASE_URL", failures)
    require_env(f"{prefix}_API_KEY", failures)
    require_env(f"{prefix}_MODEL_NAME", failures)


def require_search_provider_config(failures: list[str]) -> None:
    provider = (env_value("SEARCH_TOOL_TYPE") or "AnspireAPI").strip()
    if provider == "BochaAPI":
        require_env("BOCHA_WEB_SEARCH_API_KEY", failures)
        return
    if provider == "TavilyAPI":
        require_env("TAVILY_API_KEY", failures)
        return
    if provider == "AnspireAPI":
        require_env("ANSPIRE_API_KEY", failures)
        return
    print(f"MISSING SEARCH_TOOL_TYPE: unsupported provider {provider}")
    failures.append(f"Unsupported SEARCH_TOOL_TYPE: {provider}")


def require_import(
    module_name: str, package_name: str, failures: list[str]
) -> None:
    if importlib.util.find_spec(module_name) is not None:
        print(f"OK import {module_name}: available")
        return
    print(f"MISSING import {module_name}")
    failures.append(
        f"Python package {package_name} is required in the backend environment"
    )


def env_value(name: str) -> str:
    value = os.environ.get(name, "")
    return value.strip()


if __name__ == "__main__":
    sys.exit(main())
