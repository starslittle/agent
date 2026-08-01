import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ShieldX } from "lucide-react";

import { QidianWordmark } from "@/brand/QidianMark";
import { useAuth } from "./AuthProvider";
import { hasObservabilityAccess } from "./observability-access";

export function ObservabilityRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-background text-foreground">
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">正在确认内部访问权限</p>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!hasObservabilityAccess(user)) {
    return (
      <main className="grid min-h-screen place-items-center bg-background px-6 text-foreground">
        <div className="w-full max-w-md rounded-3xl border border-border bg-card p-8 text-center shadow-sm">
          <div className="flex justify-center"><QidianWordmark /></div>
          <ShieldX className="mx-auto mt-8 h-8 w-8 text-destructive" aria-hidden="true" />
          <h1 className="mt-4 text-lg font-semibold">无内部观测权限</h1>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">这个页面仅供已授权的只读观测人员使用。</p>
          <a href="/" className="mt-6 inline-flex min-h-11 items-center rounded-xl bg-primary px-5 text-sm font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-ring/25">返回工作区</a>
        </div>
      </main>
    );
  }
  return children;
}
