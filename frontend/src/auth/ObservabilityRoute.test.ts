import { describe, expect, it } from "vitest";

import type { AuthUser } from "@/lib/auth-api";
import { hasObservabilityAccess } from "./observability-access";

const baseUser: AuthUser = {
  id: "user-1",
  email: "user@example.com",
  display_name: "User",
  status: "active",
  role: "user",
  created_at: "2026-08-01T00:00:00Z",
};

describe("observability permission", () => {
  it("denies normal and signed-out users", () => {
    expect(hasObservabilityAccess(baseUser)).toBe(false);
    expect(hasObservabilityAccess(null)).toBe(false);
  });

  it("allows only observability admins", () => {
    expect(hasObservabilityAccess({ ...baseUser, role: "observability_admin" })).toBe(true);
  });
});
