import assert from "node:assert/strict";
import test from "node:test";
import { argusSystemPrompt } from "./prompts";

const requestHints = {
  latitude: undefined,
  longitude: undefined,
  city: undefined,
  country: undefined,
};

test("Argus prompt includes concise webSearch guidance", () => {
  const prompt = argusSystemPrompt({ requestHints, supportsTools: true });

  assert.match(
    prompt,
    /Use webSearch when public context can clarify the research request\./
  );
  assert.match(
    prompt,
    /Treat search-derived details as unconfirmed until the user accepts them\./
  );
  assert.doesNotMatch(prompt, /For a single-turn request/);
});

test("Argus prompt keeps profile guidance concise", () => {
  const prompt = argusSystemPrompt({ requestHints, supportsTools: true });

  assert.match(prompt, /Collect these fields:/);
  assert.match(prompt, /analysis profile/);
  assert.match(prompt, /Profile:/);
  assert.match(prompt, /artist_management/);
  assert.match(prompt, /enterprise_pr/);
  assert.doesNotMatch(prompt, /car owners|automotive-specific/i);
});
