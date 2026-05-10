/**
 * StatusChip — semantic status pill (cooking / delivered / pending / urgent / etc).
 * Internally a tightly-toned <Pill>. Use this when the visual is reading a state,
 * not a generic tag.
 */

import React from "react";
import { Pill, type PillSize } from "./Pill";
import { Ionicons } from "@expo/vector-icons";

export type ChipStatus =
  | "cooking"
  | "delivered"
  | "pending"
  | "urgent"
  | "approved"
  | "rejected"
  | "ordered"
  | "in_stock"
  | "low_stock"
  | "missing"
  | "winner"
  | "new"
  | "auto"
  | "info";

const MAP: Record<ChipStatus, { tone: React.ComponentProps<typeof Pill>["tone"]; icon?: keyof typeof Ionicons.glyphMap; label?: string }> = {
  cooking:   { tone: "primary",  icon: "flame", label: "Cooking" },
  delivered: { tone: "success",  icon: "checkmark-done-circle", label: "Delivered" },
  pending:   { tone: "warning",  icon: "hourglass-outline", label: "Pending" },
  urgent:    { tone: "danger",   icon: "alert-circle", label: "Urgent" },
  approved:  { tone: "success",  icon: "checkmark-circle", label: "Approved" },
  rejected:  { tone: "danger",   icon: "close-circle", label: "Rejected" },
  ordered:   { tone: "info",     icon: "cart", label: "Ordered" },
  in_stock:  { tone: "success",  icon: "checkmark-circle", label: "In stock" },
  low_stock: { tone: "warning",  icon: "warning", label: "Low" },
  missing:   { tone: "danger",   icon: "close-circle", label: "Missing" },
  winner:    { tone: "success",  icon: "trophy", label: "Winner" },
  new:       { tone: "primary",  icon: "sparkles", label: "New" },
  auto:      { tone: "info",     icon: "flash", label: "Auto" },
  info:      { tone: "info" },
};

export interface StatusChipProps {
  status: ChipStatus;
  /** Override the default label (e.g., for "Approved by Anjan"). */
  label?: string;
  size?: PillSize;
  showIcon?: boolean;
}

export function StatusChip({ status, label, size = "sm", showIcon = true }: StatusChipProps) {
  const cfg = MAP[status];
  const text = label ?? cfg.label ?? "";
  return (
    <Pill tone={cfg.tone} size={size} leadingIcon={showIcon ? cfg.icon : undefined}>
      {text}
    </Pill>
  );
}
