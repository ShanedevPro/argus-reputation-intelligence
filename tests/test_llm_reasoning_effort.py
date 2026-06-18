from types import SimpleNamespace

import pytest


REASONING_ENV_VARS = [
    "LLM_REASONING_EFFORT",
    "QUERY_ENGINE_REASONING_EFFORT",
    "MEDIA_ENGINE_REASONING_EFFORT",
    "INSIGHT_ENGINE_REASONING_EFFORT",
    "REPORT_ENGINE_REASONING_EFFORT",
    "FORUM_HOST_REASONING_EFFORT",
]


class CaptureOpenAI:
    def __init__(self, **_kwargs):
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("stream"):
            return iter(
                [
                    SimpleNamespace(
                        choices=[
                            SimpleNamespace(delta=SimpleNamespace(content="streamed"))
                        ]
                    )
                ]
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=" completed "))
            ]
        )


def clear_reasoning_env(monkeypatch):
    for env_name in REASONING_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)


@pytest.mark.parametrize(
    ("module_name", "engine_env_name"),
    [
        ("QueryEngine.llms.base", "QUERY_ENGINE_REASONING_EFFORT"),
        ("MediaEngine.llms.base", "MEDIA_ENGINE_REASONING_EFFORT"),
        ("InsightEngine.llms.base", "INSIGHT_ENGINE_REASONING_EFFORT"),
        ("ReportEngine.llms.base", "REPORT_ENGINE_REASONING_EFFORT"),
    ],
)
def test_engine_specific_reasoning_effort_is_passed(
    monkeypatch, module_name, engine_env_name
):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv(engine_env_name, "xhigh")

    module = pytest.importorskip(module_name)
    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(module, "OpenAI", lambda **kwargs: fake_openai)

    client = module.LLMClient(api_key="test-key", model_name="gpt-5.5", base_url="https://example.test/v1")
    assert client.invoke("system", "user") == "completed"

    assert fake_openai.calls[0]["reasoning_effort"] == "xhigh"


def test_global_reasoning_effort_is_used_when_engine_specific_is_unset(monkeypatch):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv("LLM_REASONING_EFFORT", "high")

    from QueryEngine.llms import base as query_llm

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(query_llm, "OpenAI", lambda **kwargs: fake_openai)

    client = query_llm.LLMClient(api_key="test-key", model_name="gpt-5.5")
    client.invoke("system", "user")

    assert fake_openai.calls[0]["reasoning_effort"] == "high"


def test_default_omits_reasoning_effort(monkeypatch):
    clear_reasoning_env(monkeypatch)

    from ReportEngine.llms import base as report_llm

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(report_llm, "OpenAI", lambda **kwargs: fake_openai)

    client = report_llm.LLMClient(api_key="test-key", model_name="gpt-5.5")
    client.invoke("system", "user")

    assert "reasoning_effort" not in fake_openai.calls[0]


def test_streaming_call_uses_configured_reasoning_effort(monkeypatch):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv("REPORT_ENGINE_REASONING_EFFORT", "medium")

    from ReportEngine.llms import base as report_llm

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(report_llm, "OpenAI", lambda **kwargs: fake_openai)

    client = report_llm.LLMClient(api_key="test-key", model_name="gpt-5.5")
    assert list(client.stream_invoke("system", "user")) == ["streamed"]

    assert fake_openai.calls[0]["reasoning_effort"] == "medium"


def test_report_engine_call_reasoning_effort_overrides_default(monkeypatch):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv("REPORT_ENGINE_REASONING_EFFORT", "xhigh")

    from ReportEngine.llms import base as report_llm

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(report_llm, "OpenAI", lambda **kwargs: fake_openai)

    client = report_llm.LLMClient(api_key="test-key", model_name="gpt-5.5")
    assert list(client.stream_invoke("system", "user", reasoning_effort="high")) == ["streamed"]

    assert fake_openai.calls[0]["reasoning_effort"] == "high"


def test_report_engine_call_reasoning_effort_none_omits_default(monkeypatch):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv("REPORT_ENGINE_REASONING_EFFORT", "xhigh")

    from ReportEngine.llms import base as report_llm

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(report_llm, "OpenAI", lambda **kwargs: fake_openai)

    client = report_llm.LLMClient(api_key="test-key", model_name="gpt-5.5")
    client.invoke("system", "user", reasoning_effort="none")

    assert "reasoning_effort" not in fake_openai.calls[0]


def test_invalid_reasoning_effort_raises_clear_error(monkeypatch):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv("REPORT_ENGINE_REASONING_EFFORT", "turbo")

    from ReportEngine.llms import base as report_llm

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(report_llm, "OpenAI", lambda **kwargs: fake_openai)

    with pytest.raises(ValueError, match="REPORT_ENGINE_REASONING_EFFORT"):
        report_llm.LLMClient(api_key="test-key", model_name="gpt-5.5")

    assert fake_openai.calls == []


def test_none_reasoning_effort_omits_param(monkeypatch):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv("REPORT_ENGINE_REASONING_EFFORT", "none")

    from ReportEngine.llms import base as report_llm

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(report_llm, "OpenAI", lambda **kwargs: fake_openai)

    client = report_llm.LLMClient(api_key="test-key", model_name="gpt-5.5")
    client.invoke("system", "user")

    assert "reasoning_effort" not in fake_openai.calls[0]


def test_forum_host_uses_configured_reasoning_effort(monkeypatch):
    clear_reasoning_env(monkeypatch)
    monkeypatch.setenv("FORUM_HOST_REASONING_EFFORT", "xhigh")

    from ForumEngine import llm_host

    fake_openai = CaptureOpenAI()
    monkeypatch.setattr(llm_host, "OpenAI", lambda **kwargs: fake_openai)

    host = llm_host.ForumHost(
        api_key="test-key",
        base_url="https://example.test/v1",
        model_name="gpt-5.5",
    )
    result = host._call_qwen_api("system", "user")

    assert result["success"] is True
    assert fake_openai.calls[0]["reasoning_effort"] == "xhigh"
