import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  fetchSession,
  login as loginRequest,
  logout as logoutRequest,
  register as registerRequest,
  type AuthSession,
  type AuthUser,
  type LoginInput,
  type RegisterInput,
} from "@/lib/auth-api";

interface AuthContextValue {
  user: AuthUser | null;
  csrfToken: string;
  loading: boolean;
  login: (input: LoginInput) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [csrfToken, setCSRFToken] = useState("");
  const [loading, setLoading] = useState(true);

  const applySession = useCallback((session: AuthSession) => {
    if (session.authenticated && session.user && session.csrf_token) {
      setUser(session.user);
      setCSRFToken(session.csrf_token);
      return;
    }
    setUser(null);
    setCSRFToken("");
  }, []);

  const refresh = useCallback(async () => {
    try {
      applySession(await fetchSession());
    } catch {
      setUser(null);
      setCSRFToken("");
    } finally {
      setLoading(false);
    }
  }, [applySession]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (input: LoginInput) => {
    applySession(await loginRequest(input));
  }, [applySession]);

  const register = useCallback(async (input: RegisterInput) => {
    applySession(await registerRequest(input));
  }, [applySession]);

  const logout = useCallback(async () => {
    try {
      if (csrfToken) {
        await logoutRequest(csrfToken);
      }
    } catch {
      // Local logout remains safe and useful when the server is unreachable.
    } finally {
      setUser(null);
      setCSRFToken("");
    }
  }, [csrfToken]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    csrfToken,
    loading,
    login,
    register,
    logout,
    refresh,
  }), [csrfToken, loading, login, logout, refresh, register, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
