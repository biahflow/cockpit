import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

import { currentUser, getConfig, login as loginRequest, logout as logoutRequest } from "./api";
import type { AppConfig, SessionUser } from "./types";

type AuthContextValue = {
  user: SessionUser | null;
  isLoading: boolean;
  aiEnabled: boolean;
  calendarEnabled: boolean;
  esignEnabled: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Recarrega o usuário da sessão a partir de `/auth/me/`.
   *
   * Existe para o topbar refletir nome e foto novos **sem recarregar a página**: `setUser` é
   * local ao provider, então uma tela que edita o próprio perfil não tinha como avisar o shell
   * de que o dado que ele desenha mudou. */
  refreshUser: () => Promise<void>;
};

const EMPTY_CONFIG: AppConfig = { ai_enabled: false, calendar_enabled: false, esign_enabled: false, integrations: [] };

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [config, setConfig] = useState<AppConfig>(EMPTY_CONFIG);

  useEffect(() => {
    currentUser().then(setUser).catch(() => setUser(null)).finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    if (!user) return;
    getConfig().then(setConfig).catch(() => setConfig(EMPTY_CONFIG));
  }, [user]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    isLoading,
    aiEnabled: user ? config.ai_enabled : false,
    calendarEnabled: user ? config.calendar_enabled : false,
    esignEnabled: user ? config.esign_enabled : false,
    async login(username, password) { setUser(await loginRequest(username, password)); },
    async logout() { await logoutRequest(); setUser(null); },
    async refreshUser() { setUser(await currentUser()); },
  }), [isLoading, user, config]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth deve ser usado dentro de AuthProvider.");
  return context;
}
