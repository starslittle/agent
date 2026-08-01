import { Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { WorkspaceLoadingScreen } from "@/components/workspace/WorkspaceShell";
import { useAuth } from "./AuthProvider";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <WorkspaceLoadingScreen label="正在确认身份…" />;
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
