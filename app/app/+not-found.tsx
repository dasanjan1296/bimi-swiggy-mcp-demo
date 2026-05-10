/**
 * +not-found — Expo Router's catch-all for any URL that doesn't match
 * a registered route. Without this file, Expo Router renders its
 * default black "Unmatched Route — Page could not be found" screen,
 * which a real user would see whenever:
 *
 *   - A push-notification payload from an older app version targets a
 *     route that's since been deleted (e.g., the 2026-05-03 redesign
 *     retired /(tabs)/voting, /(tabs)/approvals, /(tabs)/kitchen and
 *     about a dozen other screens — see app/_layout.tsx).
 *   - A legacy bimi:// universal link saved by a user goes stale.
 *   - Hot-reload during development lands the app on a route the new
 *     bundle doesn't know about.
 *
 * The cure is to silently `<Redirect>` to the Today tab. The user
 * never sees the error screen; they land on the home surface where
 * they can pick up whatever they meant to do. We don't surface a
 * toast or any "that link is gone" microcopy — most users don't know
 * what they tapped, and a quiet redirect is the calmer behaviour.
 *
 * If a screen NEEDS to know it was reached by a stale path (e.g., to
 * deep-link further from there), we'd add a query param here and
 * read it on Today. Not yet warranted.
 */

import { Redirect } from "expo-router";

export default function NotFound() {
  return <Redirect href="/(tabs)" />;
}
