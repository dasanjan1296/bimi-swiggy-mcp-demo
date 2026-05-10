/**
 * useTabBarPadding — returns a `paddingBottom` value that clears the floating
 * tab bar (height 56 + insets.bottom, defined in `(tabs)/_layout.tsx`) plus a
 * gap so the last card or CTA doesn't kiss the divider.
 *
 * Use on every ScrollView/FlatList contentContainerStyle inside the tabs:
 *
 *     contentContainerStyle={{ paddingBottom: useTabBarPadding() }}
 *
 * Pass `extra` to add additional clearance for sticky elements (e.g., a
 * floating CTA bar sitting above the tab bar):
 *
 *     paddingBottom: useTabBarPadding({ extra: 64 })
 *
 * QA-006 root-cause fix: the previous `paddingBottom: 120` was a magic
 * number that worked on iPhone 14 (insets.bottom ≈ 34) and broke on iPhone 17
 * Pro Max (insets.bottom ≈ 44+). This computes from the source of truth.
 */

import { useSafeAreaInsets } from "react-native-safe-area-context";
import { spacing } from "@/lib/theme";

// Floating tab bar's actual height is 56 (intrinsic) + insets.bottom. Pass 4
// G1 fix: bumped the comfort gap from spacing.lg (16) → spacing.xxl (32) so
// the last card/CTA never appears half-eaten by the translucent tab bar
// when the user scrolls to the bottom.
const TAB_BAR_INTRINSIC = 56;
const COMFORT_GAP = 32; // was spacing.lg (16) — too tight on iPhone 17 Pro

export function useTabBarPadding(opts?: { extra?: number }) {
  const insets = useSafeAreaInsets();
  return TAB_BAR_INTRINSIC + insets.bottom + COMFORT_GAP + (opts?.extra ?? 0);
}
