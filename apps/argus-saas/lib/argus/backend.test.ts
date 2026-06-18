import assert from "node:assert/strict";
import test from "node:test";
import {
  getBackendBaseUrl,
  proxyArgusBackendRequest,
} from "./backend";

function restoreEnv(name: string, value: string | undefined) {
  if (value === undefined) {
    delete process.env[name];
    return;
  }
  process.env[name] = value;
}

test("getBackendBaseUrl defaults to local Flask", () => {
  const original = process.env.BETTAFISH_BACKEND_URL;
  const originalPublic = process.env.NEXT_PUBLIC_BETTAFISH_BACKEND_URL;
  delete process.env.BETTAFISH_BACKEND_URL;
  delete process.env.NEXT_PUBLIC_BETTAFISH_BACKEND_URL;

  try {
    assert.equal(getBackendBaseUrl(), "http://127.0.0.1:5000");
  } finally {
    restoreEnv("BETTAFISH_BACKEND_URL", original);
    restoreEnv("NEXT_PUBLIC_BETTAFISH_BACKEND_URL", originalPublic);
  }
});

test("getBackendBaseUrl prefers server-only backend URL", () => {
  const original = process.env.BETTAFISH_BACKEND_URL;
  const originalPublic = process.env.NEXT_PUBLIC_BETTAFISH_BACKEND_URL;
  process.env.BETTAFISH_BACKEND_URL = "http://server.local:5000";
  process.env.NEXT_PUBLIC_BETTAFISH_BACKEND_URL = "http://public.local:5000";

  try {
    assert.equal(getBackendBaseUrl(), "http://server.local:5000");
  } finally {
    restoreEnv("BETTAFISH_BACKEND_URL", original);
    restoreEnv("NEXT_PUBLIC_BETTAFISH_BACKEND_URL", originalPublic);
  }
});

test("proxyArgusBackendRequest forwards JSON and status", async () => {
  const originalFetch = globalThis.fetch;
  const originalBackend = process.env.BETTAFISH_BACKEND_URL;
  const calls: Array<{ url: string; init?: RequestInit }> = [];

  process.env.BETTAFISH_BACKEND_URL = "http://backend.local";
  globalThis.fetch = (async (url: string | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ ok: true }), {
      status: 202,
      headers: { "content-type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const response = await proxyArgusBackendRequest("/api/crawl/tasks", {
      method: "POST",
      body: JSON.stringify({ query: "事件" }),
    });
    assert.equal(response.status, 202);
    assert.equal(calls[0]?.url, "http://backend.local/api/crawl/tasks");
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.equal(response.headers.get("content-type"), "application/json");
  } finally {
    globalThis.fetch = originalFetch;
    restoreEnv("BETTAFISH_BACKEND_URL", originalBackend);
  }
});
