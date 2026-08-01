import type { AuthUser } from "@/lib/auth-api";

export function hasObservabilityAccess(user: AuthUser | null): boolean {
  return user?.role === "observability_admin";
}
