import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

export function useAuth() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (api.isAuthenticated()) {
      api.verifyAuth()
        .then(() => setIsAuthenticated(true))
        .catch(() => {
          api.clearToken();
          setIsAuthenticated(false);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = useCallback(async (password: string) => {
    await api.login(password);
    setIsAuthenticated(true);
  }, []);

  const logout = useCallback(() => {
    api.clearToken();
    setIsAuthenticated(false);
  }, []);

  return { isAuthenticated, loading, login, logout };
}

export function usePolling<T>(fetcher: () => Promise<T>, intervalMs = 5000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (e) {
      setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { data, error, loading, refresh };
}
