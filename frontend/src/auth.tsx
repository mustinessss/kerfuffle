import { useEffect, useMemo, useState } from "react";
import type { PropsWithChildren } from "react";
import { ApiError, getCurrentAccount, loginWithPassword, logoutFromAccount } from "./api";
import { AuthContext } from "./authContext";
import type { AuthContextValue } from "./authContext";
import type { CurrentAccount } from "./api";

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<CurrentAccount | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getCurrentAccount()
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .catch((requestError: unknown) => {
        if (!active) return;
        if (!(requestError instanceof ApiError && requestError.status === 401)) {
          setError(requestError instanceof ApiError
            ? requestError.message
            : "Не удалось проверить сессию. Проверьте подключение и повторите попытку.");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    loading,
    error,
    async login(email, password) {
      setError("");
      try {
        setUser(await loginWithPassword(email, password));
      } catch (requestError) {
        const message = requestError instanceof ApiError
          ? requestError.message
          : "Не удалось войти. Проверьте подключение и повторите попытку.";
        setError(message);
        throw requestError;
      }
    },
    async logout() {
      setError("");
      try {
        await logoutFromAccount();
        setUser(null);
      } catch (requestError) {
        setError(requestError instanceof ApiError
          ? requestError.message
          : "Не удалось завершить сеанс.");
      }
    },
    clearError() {
      setError("");
    },
  }), [error, loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
