import { useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import type { User } from "oidc-client-ts";
import { AuthContext } from "./authContext";
import type { AuthContextValue } from "./authContext";
import { completeSigninCallback, oidcConfigured, userManager } from "./authClient";

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(oidcConfigured);
  const [error, setError] = useState("");

  useEffect(() => {
    const manager = userManager;
    if (!manager) return;
    let active = true;
    const handleUserLoaded = (loadedUser: User) => setUser(loadedUser);
    const handleUserUnloaded = () => setUser(null);
    const handleTokenExpired = () => {
      setUser(null);
      setError("Сессия завершилась. Войдите снова.");
    };

    manager.events.addUserLoaded(handleUserLoaded);
    manager.events.addUserUnloaded(handleUserUnloaded);
    manager.events.addAccessTokenExpired(handleTokenExpired);

    async function initialize(activeManager: NonNullable<typeof userManager>) {
      try {
        if (window.location.pathname === "/auth/callback") {
          const signedInUser = await completeSigninCallback();
          if (!active) return;
          setUser(signedInUser ?? null);
          const requestedReturnTo = signedInUser?.state
            && typeof signedInUser.state === "object"
            && "returnTo" in signedInUser.state
            && typeof signedInUser.state.returnTo === "string"
            ? signedInUser.state.returnTo
            : "/organizer";
          const returnUrl = new URL(requestedReturnTo, window.location.origin);
          window.location.replace(
            returnUrl.origin === window.location.origin && returnUrl.pathname !== "/auth/callback"
              ? returnUrl.href
              : "/organizer",
          );
          return;
        }

        const storedUser = await activeManager.getUser();
        if (active) setUser(storedUser?.expired ? null : storedUser);
      } catch {
        if (active) setError("Не удалось выполнить вход через Keycloak. Проверьте настройки и попробуйте снова.");
      } finally {
        if (active) setLoading(false);
      }
    }

    void initialize(manager);
    return () => {
      active = false;
      manager.events.removeUserLoaded(handleUserLoaded);
      manager.events.removeUserUnloaded(handleUserUnloaded);
      manager.events.removeAccessTokenExpired(handleTokenExpired);
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    error,
    async login() {
      if (!userManager) {
        setError("Вход не настроен: задайте VITE_OIDC_AUTHORITY и VITE_OIDC_CLIENT_ID.");
        return;
      }
      setError("");
      try {
        await userManager.signinRedirect({
          state: { returnTo: `${window.location.pathname}${window.location.search}` },
        });
      } catch {
        setError("Не удалось открыть страницу входа Keycloak. Проверьте адрес провайдера.");
      }
    },
    async logout() {
      if (!userManager) {
        setUser(null);
        return;
      }
      try {
        await userManager.signoutRedirect();
      } catch {
        setError("Не удалось завершить сеанс в Keycloak.");
      }
    },
    clearError() {
      setError("");
    },
  }), [error, loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
