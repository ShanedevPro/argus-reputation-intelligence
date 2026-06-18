"use server";

import { isTestEnvironment } from "@/lib/constants";
import { getSuggestionsByDocumentId } from "@/lib/db/queries";

export async function getSuggestions({ documentId }: { documentId: string }) {
  if (isTestEnvironment) {
    return [];
  }

  const suggestions = await getSuggestionsByDocumentId({ documentId });
  return suggestions ?? [];
}
