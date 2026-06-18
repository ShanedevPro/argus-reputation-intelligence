import assert from "node:assert/strict";
import test from "node:test";
import { getLanguageModel, getTitleModel } from "./providers";

const ENV_KEYS = [
  "ARGUS_CHAT_BASE_URL",
  "ARGUS_CHAT_API_KEY",
  "ARGUS_CHAT_MODEL",
  "ARGUS_CHAT_TITLE_MODEL",
  "QUERY_ENGINE_BASE_URL",
  "QUERY_ENGINE_API_KEY",
  "QUERY_ENGINE_MODEL_NAME",
  "REPORT_ENGINE_BASE_URL",
  "REPORT_ENGINE_API_KEY",
  "REPORT_ENGINE_MODEL_NAME",
  "INSIGHT_ENGINE_BASE_URL",
  "INSIGHT_ENGINE_API_KEY",
  "INSIGHT_ENGINE_MODEL_NAME",
  "MEDIA_ENGINE_BASE_URL",
  "MEDIA_ENGINE_API_KEY",
  "MEDIA_ENGINE_MODEL_NAME",
  "OPENAI_BASE_URL",
  "OPENAI_API_KEY",
  "AI_GATEWAY_API_KEY",
  "ZAI_API_KEY",
  "ZHIPU_API_KEY",
  "GLM_API_KEY",
  "GLM_CODEPLAN_MBLY_API_KEY",
  "GLM_CODEPLAN_LY_API_KEY",
] as const;

function withEnv(
  values: Partial<Record<(typeof ENV_KEYS)[number], string>>,
  run: () => void
) {
  const original = new Map<string, string | undefined>();
  for (const key of ENV_KEYS) {
    original.set(key, process.env[key]);
    delete process.env[key];
  }
  Object.assign(process.env, values);

  try {
    run();
  } finally {
    for (const key of ENV_KEYS) {
      const value = original.get(key);
      if (value === undefined) {
        delete process.env[key];
      } else {
        process.env[key] = value;
      }
    }
  }
}

test("getLanguageModel uses Argus chat OpenAI-compatible config", () => {
  withEnv(
    {
      ARGUS_CHAT_BASE_URL: "https://argus-chat.example/v1",
      ARGUS_CHAT_API_KEY: "argus-key",
      ARGUS_CHAT_MODEL: "mimo/mimo-v2.5-pro",
      AI_GATEWAY_API_KEY: "gateway-key",
    },
    () => {
      const model = getLanguageModel("mimo/mimo-v2.5-pro") as {
        provider: string;
        modelId: string;
      };

      assert.equal(model.provider, "argus-chat.chat");
      assert.equal(model.modelId, "mimo/mimo-v2.5-pro");
    }
  );
});

test("getTitleModel uses configured Argus title model", () => {
  withEnv(
    {
      ARGUS_CHAT_BASE_URL: "https://argus-chat.example/v1",
      ARGUS_CHAT_API_KEY: "argus-key",
      ARGUS_CHAT_MODEL: "mimo/mimo-v2.5-pro",
      ARGUS_CHAT_TITLE_MODEL: "mimo-title-model",
    },
    () => {
      const model = getTitleModel() as { provider: string; modelId: string };

      assert.equal(model.provider, "argus-chat.chat");
      assert.equal(model.modelId, "mimo-title-model");
    }
  );
});

test("provider throws a clear configuration error instead of falling back to Gateway", () => {
  withEnv({ AI_GATEWAY_API_KEY: "gateway-key" }, () => {
    assert.throws(
      () => getLanguageModel("mimo/mimo-v2.5-pro"),
      /Argus chat provider is not configured/
    );
  });
});
