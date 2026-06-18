const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:5000";

export function getBackendBaseUrl() {
  return (
    process.env.BETTAFISH_BACKEND_URL ??
    process.env.NEXT_PUBLIC_BETTAFISH_BACKEND_URL ??
    DEFAULT_BACKEND_BASE_URL
  );
}

export async function proxyArgusBackendRequest(
  path: string,
  init: RequestInit = {}
) {
  const backendUrl = new URL(path, getBackendBaseUrl());
  const headers = new Headers(init.headers);

  if (!headers.has("accept")) {
    headers.set("accept", "application/json");
  }

  const response = await fetch(backendUrl, {
    ...init,
    headers,
    cache: "no-store",
  });

  const body = await response.text();
  const contentType =
    response.headers.get("content-type") ?? "application/json; charset=utf-8";

  return new Response(body, {
    status: response.status,
    headers: {
      "cache-control": "no-store",
      "content-type": contentType,
    },
  });
}
