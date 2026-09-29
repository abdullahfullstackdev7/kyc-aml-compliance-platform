import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "@/lib/auth";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { session, ready } = useAuth();

  if (!ready) return null;
  if (!session) return <Navigate to="/login" replace />;

  return <>{children}</>;
}
