import assert from "node:assert/strict";
import test from "node:test";
import { webSearch } from "./tools/web-search";

function restoreEnv(name: string, value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
    return;
  }
  process.env[name] = value;
}

test("webSearch posts a lightweight intake query to the backend", async () => {
  const originalFetch = globalThis.fetch;
  const originalBackend = process.env.BETTAFISH_BACKEND_URL;
  const calls: Array<{ url: string; init?: RequestInit }> = [];

  process.env.BETTAFISH_BACKEND_URL = "http://backend.local";
  globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(
      JSON.stringify({
        success: true,
        query: "王鹤棣 最近争议",
        provider: "BochaAPI",
        results: [{ title: "Result", url: "https://example.com" }],
      }),
      { status: 200, headers: { "content-type": "application/json" } }
    );
  }) as typeof fetch;

  try {
    const result = await webSearch.execute?.(
      { query: "王鹤棣 最近争议", maxResults: 7 },
      { toolCallId: "tool_1", messages: [] } as never
    );

    assert.deepEqual(result, {
      success: true,
      query: "王鹤棣 最近争议",
      provider: "BochaAPI",
      results: [{ title: "Result", url: "https://example.com" }],
    });
    assert.equal(calls[0]?.url, "http://backend.local/api/intake/web-search");
    assert.equal(calls[0]?.init?.method, "POST");
    assert.equal(
      calls[0]?.init?.body,
      JSON.stringify({ query: "王鹤棣 最近争议", max_results: 7 })
    );
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnv("BETTAFISH_BACKEND_URL", originalBackend);
  }
});

test("webSearch returns structured failure output for backend errors", async () => {
  const originalFetch = globalThis.fetch;
  const originalBackend = process.env.BETTAFISH_BACKEND_URL;

  process.env.BETTAFISH_BACKEND_URL = "http://backend.local";
  globalThis.fetch = (async () =>
    new Response(
      JSON.stringify({
        success: false,
        message: "Search provider is not configured.",
      }),
      { status: 503, headers: { "content-type": "application/json" } }
    )) as typeof fetch;

  try {
    const result = await webSearch.execute?.(
      { query: "王鹤棣 最近争议" },
      { toolCallId: "tool_1", messages: [] } as never
    );

    assert.deepEqual(result, {
      success: false,
      message: "Search provider is not configured.",
    });
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnv("BETTAFISH_BACKEND_URL", originalBackend);
  }
});
