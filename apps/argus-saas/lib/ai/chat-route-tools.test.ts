import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("chat route exposes webSearch as an active model tool", () => {
  const source = readFileSync(
    new URL("../../app/(chat)/api/chat/route.ts", import.meta.url),
    "utf8"
  );

  assert.match(source, /import \{ webSearch \} from "@\/lib\/ai\/tools\/web-search";/);
  assert.match(source, /"webSearch"/);
  assert.match(source, /tools:\s*{[\s\S]*webSearch/);
});
