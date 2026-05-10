/**
 * GlowCard — used to render a colored-shadow halo around hero cards on
 * the dark theme. Colored shadows don't translate to light surfaces — they
 * read as "smudge" rather than "elevation". The light theme overhaul
 * retired the glow effect; this component is now a thin shim that renders
 * an elevated white card and ignores the `color` prop.
 *
 * Existing callers (InlineBookingCard, InstaCookHeroCard, InstaCookStatusCard,
 * BookingReviewSheet) keep working without code changes. Migrate to
 * `<Card variant="elevated">` from `components/patterns/Card` opportunistically.
 */

import React from "react";
import { View, ViewStyle } from "react-native";
import { elevatedCardStyles } from "@/lib/theme";

export interface GlowCardProps {
  /** Deprecated — colored-shadow halos are not part of the light theme. Ignored. */
  color?: string;
  children: React.ReactNode;
  style?: ViewStyle;
  /** When false, the underlying card chrome is omitted (caller supplies its own). */
  withCardChrome?: boolean;
}

export function GlowCard({
  color: _color,
  children,
  style,
  withCardChrome = true,
}: GlowCardProps) {
  if (!withCardChrome) {
    return <View style={style}>{children}</View>;
  }
  return <View style={[elevatedCardStyles, style]}>{children}</View>;
}
