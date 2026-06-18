import { proxyArgusBackendRequest } from "@/lib/argus/backend";

export async function POST(request: Request) {
  const body = await request.text();
  return proxyArgusBackendRequest("/api/search", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
}
