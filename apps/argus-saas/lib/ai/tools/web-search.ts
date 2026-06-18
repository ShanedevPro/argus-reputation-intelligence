import { tool } from "ai";
import { z } from "zod";
import { getBackendBaseUrl } from "@/lib/argus/backend";

type WebSearchResult = {
  title?: string;
  url?: string;
  snippet?: string;
  published_at?: string | null;
  source?: string | null;
};

type WebSearchResponse = {
  success: boolean;
  query?: string;
  provider?: string;
  results?: WebSearchResult[];
  answer?: string | null;
  message?: string;
};

async function readSearchResponse(response: Response): Promise<WebSearchResponse> {
  try {
    return (await response.json()) as WebSearchResponse;
  } catch {
    return {
      success: false,
      message: `Search request failed with status ${response.status}.`,
    };
  }
}

export const webSearch = tool({
  description:
    "Search public web results to clarify an Argus reputation research intake request.",
  inputSchema: z.object({
    query: z.string().min(1).max(300),
    maxResults: z.number().int().min(1).max(8).optional(),
  }),
  execute: async ({ query, maxResults }) => {
    try {
      const response = await fetch(
        new URL("/api/intake/web-search", getBackendBaseUrl()),
        {
          method: "POST",
          headers: {
            accept: "application/json",
            "content-type": "application/json",
          },
          body: JSON.stringify({
            query,
            max_results: maxResults,
          }),
          cache: "no-store",
        }
      );

      const payload = await readSearchResponse(response);
      if (!response.ok) {
        return {
          success: false,
          message: payload.message ?? `Search request failed: ${response.status}`,
        };
      }

      return payload;
    } catch {
      return {
        success: false,
        message: "Search provider request failed.",
      };
    }
  },
});
