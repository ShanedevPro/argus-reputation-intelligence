import assert from "node:assert/strict";
import test from "node:test";
import {
  allowedModelIds,
  chatModels,
  DEFAULT_CHAT_MODEL,
  getActiveModels,
  getCapabilities,
  resolveChatModelId,
} from "./models";

const MIMO_MODEL = "mimo/mimo-v2.5-pro";

test("Argus local MVP defaults to Mimo and does not expose GLM", async () => {
  assert.equal(DEFAULT_CHAT_MODEL, MIMO_MODEL);
  assert.deepEqual(
    chatModels.map((model) => model.id),
    [MIMO_MODEL]
  );
  assert.deepEqual(
    getActiveModels().map((model) => model.id),
    [MIMO_MODEL]
  );
  assert.equal(allowedModelIds.has(MIMO_MODEL), true);
  assert.equal(allowedModelIds.has("glm-5.1"), false);

  const capabilities = await getCapabilities();
  assert.deepEqual(capabilities, {
    [MIMO_MODEL]: {
      tools: true,
      vision: false,
      reasoning: true,
    },
  });
});

test("Argus local MVP resolves stale model ids to Mimo", () => {
  assert.equal(resolveChatModelId(MIMO_MODEL), MIMO_MODEL);
  assert.equal(resolveChatModelId("glm-5.1"), MIMO_MODEL);
  assert.equal(resolveChatModelId("mistral/mistral-small-latest"), MIMO_MODEL);
  assert.equal(resolveChatModelId(undefined), MIMO_MODEL);
});
