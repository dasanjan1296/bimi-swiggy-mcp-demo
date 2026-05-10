/**
 * AmbientBackdrop — formerly drove drifting amber/violet blur blobs behind
 * every screen on the dark theme. The light theme finds atmosphere in
 * whitespace and dish photography rather than tinted backgrounds; this
 * component now renders nothing.
 *
 * Existing callers (SafeScreen) keep working without code changes. Future
 * agents: don't reach for this when "the screen feels flat" — use
 * `<PhotoCard>` or breathing `spacing.xxl` margins instead.
 */

import React from "react";

export type AmbientVariant = "default" | "calm" | "celebration" | "none";

export interface AmbientBackdropProps {
  variant?: AmbientVariant;
}

export function AmbientBackdrop(_props: AmbientBackdropProps) {
  return null;
}
