import assert from "node:assert/strict";
import test from "node:test";
import {
  ARGUS_CHAT_DEFAULT_MODEL,
  getArgusChatConfig,
} from "./argus-chat-config";

function env(overrides: Record<string, string | undefined>) {
  return overrides as NodeJS.ProcessEnv;
}

test("Argus chat config prefers explicit ARGUS_CHAT values", () => {
  const config = getArgusChatConfig(
    env({
      ARGUS_CHAT_BASE_URL: "https://argus-chat.example/v1",
      ARGUS_CHAT_API_KEY: "argus-key",
      ARGUS_CHAT_MODEL: "custom-chat-model",
      ARGUS_CHAT_TITLE_MODEL: "custom-title-model",
      QUERY_ENGINE_BASE_URL: "https://query.example/v1",
      QUERY_ENGINE_API_KEY: "query-key",
      QUERY_ENGINE_MODEL_NAME: "query-model",
    })
  );

  assert.equal(config.configured, true);
  assert.equal(config.baseURL, "https://argus-chat.example/v1");
  assert.equal(config.apiKey, "argus-key");
  assert.equal(config.model, "custom-chat-model");
  assert.equal(config.titleModel, "custom-title-model");
  assert.deepEqual(config.missing, []);
});

test("Argus chat config falls back to QueryEngine Mimo settings", () => {
  const config = getArgusChatConfig(
    env({
      QUERY_ENGINE_BASE_URL: "https://query.example/v1",
      QUERY_ENGINE_API_KEY: "query-key",
      QUERY_ENGINE_MODEL_NAME: "mimo/mimo-v2.5-pro",
    })
  );

  assert.equal(config.configured, true);
  assert.equal(config.baseURL, "https://query.example/v1");
  assert.equal(config.apiKey, "query-key");
  assert.equal(config.model, "mimo/mimo-v2.5-pro");
  assert.equal(config.titleModel, "mimo/mimo-v2.5-pro");
});

test("Argus chat config falls back from QueryEngine to ReportEngine credentials", () => {
  const config = getArgusChatConfig(
    env({
      REPORT_ENGINE_BASE_URL: "https://report.example/v1",
      REPORT_ENGINE_API_KEY: "report-key",
      REPORT_ENGINE_MODEL_NAME: "mimo/mimo-v2.5-pro",
    })
  );

  assert.equal(config.configured, true);
  assert.equal(config.baseURL, "https://report.example/v1");
  assert.equal(config.apiKey, "report-key");
  assert.equal(config.model, ARGUS_CHAT_DEFAULT_MODEL);
  assert.equal(config.titleModel, ARGUS_CHAT_DEFAULT_MODEL);
});

test("Argus chat config reports missing provider pieces without secrets", () => {
  const config = getArgusChatConfig(env({}));

  assert.equal(config.configured, false);
  assert.equal(config.baseURL, undefined);
  assert.equal(config.apiKey, undefined);
  assert.deepEqual(config.missing, ["baseURL", "apiKey"]);
  assert.equal(config.model, ARGUS_CHAT_DEFAULT_MODEL);
  assert.equal(config.titleModel, ARGUS_CHAT_DEFAULT_MODEL);
});
