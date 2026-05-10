/**
 * Singleton QueryClient — exported so non-React code (auth-store logout,
 * reset-user-stores) can call .clear() / .invalidateQueries() without
 * having to thread a hook through.
 *
 * Defaults match what _layout.tsx wraps the app with. Both files MUST
 * stay in sync — _layout.tsx imports this same instance instead of
 * creating its own.
 */

import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 8000),
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: {
      retry: 0,
    },
  },
});
