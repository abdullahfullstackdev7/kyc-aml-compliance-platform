import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setAccessToken, ApiError } from "@/lib/api";
import type { LoginResponse, LoginSuccess } from "@/lib/types";

const STORAGE_KEY = "sentinelkyc-session";

interface Session {
  accessToken: string;
  refreshToken: string;
  userId: number;
  tenantId: number | null;
  roles: string[];
}

interface AuthContextValue {
  session: Session | null;
  ready: boolean;
  login: (email: string, password: string, tenantId: number) => Promise<LoginResponse>;
  verifyMfa: (userId: number, code: string, tenantId: number) => Promise<LoginSuccess>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function persist(session: Session | null) {
  try {
    if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private browsing or blocked storage: session just won't survive a reload */
  }
}

function load(): Session | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const existing = load();
    if (existing) setAccessToken(existing.accessToken);
    setSession(existing);
    setReady(true);
  }, []);

  function applySuccess(result: LoginSuccess): LoginSuccess {
    const next: Session = {
      accessToken: result.access_token,
      refreshToken: result.refresh_token,
      userId: result.user_id,
      tenantId: result.tenant_id,
      roles: result.roles,
    };
    setAccessToken(next.accessToken);
    setSession(next);
    persist(next);
    return result;
  }

  async function login(email: string, password: string, tenantId: number) {
    const result = await api.post<LoginResponse>("/api/v1/auth/login", {
      email,
      password,
      tenant_id: tenantId,
    });
    if (result.status === "success") applySuccess(result);
    return result;
  }

  async function verifyMfa(userId: number, code: string, tenantId: number) {
    const result = await api.post<LoginSuccess>("/api/v1/auth/mfa/verify", {
      user_id: userId,
      code,
      tenant_id: tenantId,
    });
    return applySuccess(result);
  }

  function logout() {
    const current = session;
    setAccessToken(null);
    setSession(null);
    persist(null);
    if (current) {
      api
        .post("/api/v1/auth/logout", { refresh_token: current.refreshToken })
        .catch(() => {
          /* best-effort revoke; the client-side session is already cleared */
        });
    }
  }

  return (
    <AuthContext.Provider value={{ session, ready, login, verifyMfa, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}
