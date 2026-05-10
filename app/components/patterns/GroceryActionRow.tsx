/**
 * GroceryActionRow — single grocery item rendered as a cart line card,
 * used by the redesigned `<CookActionsSheet>` (Swiggy MCP demo).
 *
 *   ┌─────────────────────────────────────────────────┐
 *   │ Atta                                            │   item name
 *   │ 5 kg                                            │   qty caption
 *   │                                                 │
 *   │ │ Only 2 kg left, Malti needs it for            │   reasoning,
 *   │ │ tomorrow's rotis                              │   orange left border
 *   └─────────────────────────────────────────────────┘
 *
 * Compliance note (Swiggy Builders Club rules): we deliberately do
 * NOT render `estimatedPriceInr` or `brandHint` even though the data
 * shape carries them — those values are invented today and surfacing
 * them would be "misrepresenting prices" / "misattributing where data
 * comes from". Once Swiggy MCP access is granted and we wire up real
 * pricing + brand, surfacing these is a one-line render swap.
 *
 * Falls back to a `description`-only render when the structured fields
 * (`itemName`, `quantity`, etc.) aren't populated, so legacy production
 * action items keep working until the cook-message intent extractor
 * starts emitting structured grocery records.
 */

import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import {
  colors,
  elevation,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { ActionItem } from "@/lib/types";
import { SWIGGY_ORANGE } from "./SwiggyBadge";

interface GroceryActionRowProps {
  action: ActionItem;
}

export function GroceryActionRow({ action }: GroceryActionRowProps) {
  const isStructured = !!action.itemName;
  const resolved = action.resolved;

  const titleText = isStructured
    ? action.itemName!
    : action.description;

  // Only the qty/unit is rendered. `brandHint` is reserved for the
  // MCP wire-up — see file-header compliance note.
  const qtyLine =
    isStructured && action.quantity != null
      ? `${formatQuantity(action.quantity)} ${action.unit ?? ""}`.trim()
      : null;

  return (
    <View
      style={{
        backgroundColor: colors.surface.base,
        borderRadius: radius.md,
        padding: spacing.md,
        gap: spacing.sm,
        opacity: resolved ? 0.5 : 1,
        ...elevation.low,
      }}
    >
      {/* Title row: name on left. ₹ deliberately NOT rendered — see
          file-header compliance note. */}
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.sm,
        }}
      >
        {resolved ? (
          <Ionicons
            name="checkmark-circle"
            size={iconSize.sm}
            color={colors.accent.success}
          />
        ) : null}
        <Text
          style={{ ...typography.h3, color: colors.text.primary, flex: 1 }}
          numberOfLines={1}
        >
          {titleText}
        </Text>
      </View>

      {/* Qty caption */}
      {qtyLine ? (
        <Text
          style={{ ...typography.caption, color: colors.text.secondary }}
          numberOfLines={1}
        >
          {qtyLine}
        </Text>
      ) : null}

      {/* Reasoning block — italic muted with orange left border accent */}
      {isStructured && action.reasoning ? (
        <View
          style={{
            borderLeftWidth: 2,
            borderLeftColor: SWIGGY_ORANGE,
            paddingLeft: spacing.sm,
            marginTop: 2,
          }}
        >
          <Text
            style={{
              ...typography.caption,
              color: colors.text.muted,
              fontStyle: "italic",
            }}
            numberOfLines={3}
          >
            {action.reasoning}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function formatQuantity(q: number): string {
  return Number.isInteger(q) ? String(q) : q.toString();
}
