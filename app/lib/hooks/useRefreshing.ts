/**
 * useRefreshing — minimal pull-to-refresh wiring shared across all main tabs.
 *
 * Returns `{ refreshing, onRefresh }` ready to spread into RefreshControl.
 * The optional `onRefresh` callback is invoked when the user pulls; we wait
 * `minDurationMs` (default 800ms) so the spinner doesn't flicker for in-memory
 * stores that resolve instantly. A success haptic fires on completion.
 *
 * Why we're hand-rolling instead of using the React Query refetch directly:
 * most Bimi screens read straight from Zustand stores backed by demo data,
 * so RQ's invalidate/refetch isn't always the source of truth. This hook
 * gives users the iOS-standard affordance regardless.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import * as Haptics from "expo-haptics";

export interface UseRefreshingOpts {
  onRefresh?: () => void | Promise<void>;
  minDurationMs?: number;
}

export function useRefreshing({ onRefresh, minDurationMs = 800 }: UseRefreshingOpts = {}) {
  const [refreshing, setRefreshing] = useState(false);
  // Track the trailing setTimeout + a mounted flag so we never fire
  // setRefreshing on an unmounted component (the setTimeout dwarf is
  // up to minDurationMs after the user pulls — plenty of time to
  // navigate away).
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    const startedAt = Date.now();
    try {
      await onRefresh?.();
    } catch {
      // swallow — errors are handled by individual feature code
    }
    if (!mountedRef.current) return;
    const elapsed = Date.now() - startedAt;
    const wait = Math.max(0, minDurationMs - elapsed);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      timerRef.current = null;
      if (!mountedRef.current) return;
      setRefreshing(false);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
    }, wait);
  }, [onRefresh, minDurationMs]);

  return { refreshing, onRefresh: handleRefresh };
}
