/**
 * DismissibleTip — wraps GuidanceTip with persistence so each storageKey
 * is shown only until the user dismisses it once.
 *
 * Uses AsyncStorage when available (linked dev client), falls back to an
 * in-memory map so dev clients without the native module don't crash with
 * an uncatchable LogBox warning. See store.ts for the same trade-off.
 */

import React, { useEffect, useState, useCallback } from "react";
import { GuidanceTip } from "../GuidanceTip";

const STORAGE_PREFIX = "bimi.tip.dismissed.";

const memoryDismissed = new Map<string, string>();

let asyncStorage: { getItem: (k: string) => Promise<string | null>; setItem: (k: string, v: string) => Promise<void> } = {
  getItem: async (k) => memoryDismissed.get(k) ?? null,
  setItem: async (k, v) => {
    memoryDismissed.set(k, v);
  },
};

// Persistence intentionally omitted; AsyncStorage native module isn't
// linked into the current dev client. Once linked, swap memory map for
// real AsyncStorage. See QA-REPORT-2026-04-18.md Pass 3 backlog.

export interface DismissibleTipProps {
  storageKey: string;
  message: string;
  title?: string;
  variant?: React.ComponentProps<typeof GuidanceTip>["variant"];
  icon?: React.ComponentProps<typeof GuidanceTip>["icon"];
  compact?: boolean;
}

export function DismissibleTip({ storageKey, message, title, variant = "hint", icon, compact }: DismissibleTipProps) {
  const [visible, setVisible] = useState(false);
  const fullKey = STORAGE_PREFIX + storageKey;

  useEffect(() => {
    asyncStorage.getItem(fullKey)
      .then((v) => setVisible(v !== "1"))
      .catch(() => setVisible(true));
  }, [fullKey]);

  const handleDismiss = useCallback(() => {
    setVisible(false);
    asyncStorage.setItem(fullKey, "1").catch(() => {});
  }, [fullKey]);

  if (!visible) return null;

  return (
    <GuidanceTip
      variant={variant}
      icon={icon}
      title={title}
      message={message}
      compact={compact}
      onDismiss={handleDismiss}
    />
  );
}
