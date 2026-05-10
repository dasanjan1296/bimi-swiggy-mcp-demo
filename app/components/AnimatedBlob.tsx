/**
 * AnimatedBlob — drifted amber/violet blur blobs for the dark-theme
 * "Organic Biophilic" atmosphere. The light theme retired this effect; the
 * component is preserved as a no-op shim so existing imports don't break,
 * but it renders nothing. Migrate call sites away during the screen sweep.
 */

import React from "react";

interface AnimatedBlobProps {
  color?: string;
  size: number;
  x: number;
  y: number;
  driftX?: number;
  driftY?: number;
  duration?: number;
  palette?: "primary" | "secondary";
}

export function AnimatedBlob(_props: AnimatedBlobProps) {
  return null;
}
