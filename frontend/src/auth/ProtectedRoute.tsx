import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "./AuthProvider";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#080b19] text-white grid place-items-center">
        <div className="flex items-center gap-3" role="status" aria-live="polite">
          <span className="h-2.5 w-2.5 rounded-full bg-violet-400 animate-pulse" />
          <span className="text-sm tracking-[0.2em] text-white/70">正在确认身份</span>
        </div>
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
