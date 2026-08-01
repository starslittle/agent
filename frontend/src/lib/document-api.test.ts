import { describe, expect, it } from "vitest";

import { documentExtractionIdempotencyKey } from "./document-api";

describe("document extraction idempotency", () => {
  it("reuses one key per immutable revision and creates an explicit retry key", () => {
    const stable = documentExtractionIdempotencyKey("revision-1");

    expect(documentExtractionIdempotencyKey("revision-1")).toBe(stable);
    expect(documentExtractionIdempotencyKey("revision-2")).not.toBe(stable);
    expect(documentExtractionIdempotencyKey("revision-1", "retry-1")).toBe(
      `${stable}:retry:retry-1`,
    );
  });
});
