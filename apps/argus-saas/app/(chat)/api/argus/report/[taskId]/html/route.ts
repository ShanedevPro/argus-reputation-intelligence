import { proxyArgusBackendRequest } from "@/lib/argus/backend";

type RouteContext = {
  params: Promise<{ taskId: string }>;
};

export async function GET(_request: Request, { params }: RouteContext) {
  const { taskId } = await params;
  return proxyArgusBackendRequest(
    `/api/report/result/${encodeURIComponent(taskId)}`,
    {
      headers: { accept: "text/html" },
    }
  );
}
