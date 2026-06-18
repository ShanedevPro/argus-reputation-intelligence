"""Optional reasoning-effort passthrough for OpenAI-compatible LLM calls."""

from __future__ import annotations

import os
from typing import Dict, Optional


ALLOWED_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}


def _normalize_reasoning_effort(value: str, context_name: str) -> Optional[str]:
    """Normalize a configured reasoning effort value."""
    normalized = (value or "").strip().lower()
    if not normalized:
        return None
    if normalized == "none":
        return None
    if normalized not in ALLOWED_REASONING_EFFORTS:
        allowed_values = sorted(ALLOWED_REASONING_EFFORTS | {"none"})
        raise ValueError(
            f"{context_name} must be one of "
            f"{', '.join(allowed_values)}; got {value!r}"
        )
    return normalized


def get_reasoning_effort(engine_env_name: str) -> Optional[str]:
    """Resolve and validate engine-specific or global reasoning effort."""
    value = os.getenv(engine_env_name) or os.getenv("LLM_REASONING_EFFORT") or ""
    return _normalize_reasoning_effort(value, engine_env_name)


def reasoning_effort_params(
    engine_env_name: str,
    override: Optional[str] = None,
) -> Dict[str, str]:
    """Return Chat Completions kwargs for reasoning effort, if configured."""
    if override is not None:
        effort = _normalize_reasoning_effort(override, "reasoning_effort")
    else:
        effort = get_reasoning_effort(engine_env_name)
    if effort is None:
        return {}
    return {"reasoning_effort": effort}


def reasoning_effort_params_from_env(env_name: str) -> Dict[str, str]:
    """Return reasoning kwargs from a single env var without global fallback."""
    value = os.getenv(env_name)
    if value is None:
        return {}
    effort = _normalize_reasoning_effort(value, env_name)
    if effort is None:
        return {}
    return {"reasoning_effort": effort}
