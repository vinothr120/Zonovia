import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, tokenStore } from "../core/apiClient";
import type { Me } from "./types";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

interface AuthContextValue {
  me: Me | null;
  status: "loading" | "authenticated" | "anonymous";
  login: (tenantSlug: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [status, setStatus] = useState<AuthContextValue["status"]>("loading");

  const loadMe = useCallback(async () => {
    if (!tokenStore.getAccessToken()) {
      setMe(null);
      setStatus("anonymous");
      return;
    }
    try {
      const data = await api.get<Me>("/users/me");
      setMe(data);
      setStatus("authenticated");
    } catch {
      tokenStore.clear();
      setMe(null);
      setStatus("anonymous");
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  const login = useCallback(
    async (tenantSlug: string, email: string, password: string) => {
      const tokens = await api.post<TokenResponse>(
        "/auth/login",
        { tenant_slug: tenantSlug, email, password },
        { skipAuth: true },
      );
      tokenStore.setTokens(tokens.access_token, tokens.refresh_token);
      await loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    const refreshToken = tokenStore.getRefreshToken();
    tokenStore.clear();
    setMe(null);
    setStatus("anonymous");
    if (refreshToken) {
      try {
        await api.post("/auth/logout", { refresh_token: refreshToken }, { skipAuth: true });
      } catch {
        // best-effort — the client-side token is already cleared either way
      }
    }
  }, []);

  const value = useMemo(
    () => ({ me, status, login, logout, refreshMe: loadMe }),
    [me, status, login, logout, loadMe],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
