import { proxyArgusBackendRequest } from "@/lib/argus/backend";

export async function POST(request: Request) {
  const body = await request.text();
  return proxyArgusBackendRequest("/api/crawl/tasks", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
}
