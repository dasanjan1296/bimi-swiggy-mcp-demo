/**
 * Safe back-navigation — wraps `router.back()` with a `canGoBack()`
 * guard and a route-level fallback. Without this guard, calling
 * `router.back()` on a screen that has nothing on its history stack
 * (cold-launch deep link, dev hot reload, push-notification entry)
 * throws the "The action 'GO_BACK' was not handled by any navigator"
 * console error AND leaves the user stranded with a back chevron
 * that does nothing.
 *
 * Use this in every stack screen's back affordance:
 *
 *   onPress={() => safeBack()}                  // → falls back to /(tabs)
 *   onPress={() => safeBack("/(tabs)/settings") // → falls back to settings
 *
 * The shared primitives `<ScreenHeader>` and `<WizardLayout>` route
 * their default back through this helper, so any screen built on top
 * of them inherits the safe behaviour for free. New screens that hand-
 * roll a back chevron MUST use `safeBack()`, never raw `router.back()`.
 */

import { router } from "expo-router";

/** The route the user lands on when there is no back history. */
const DEFAULT_FALLBACK = "/(tabs)" as const;

/**
 * Pop the navigation stack if possible, otherwise replace the route
 * with `fallback` (default `/(tabs)`). Returns `true` if a real back
 * happened, `false` if we routed to the fallback instead.
 */
export function safeBack(fallback: string = DEFAULT_FALLBACK): boolean {
  if (router.canGoBack()) {
    router.back();
    return true;
  }
  router.replace(fallback as never);
  return false;
}
