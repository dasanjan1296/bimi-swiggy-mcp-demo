/**
 * Bimi design-system showcase. Three reference screens used as living
 * documentation for the design system:
 *
 *   /(showcase)/onboarding  — single-CTA hero layout
 *   /(showcase)/dashboard   — header + hero card + photo cards + list rows
 *   /(showcase)/form        — sectioned form with input states
 *
 * These are routable in dev for visual review. Not exposed in the tab
 * bar — accessed via deep-link or via the Dev menu hookup. If a real
 * screen disagrees visually with its showcase counterpart, the real
 * screen is wrong (see design-system.md §13).
 */

import { Stack } from "expo-router";

export default function ShowcaseLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
