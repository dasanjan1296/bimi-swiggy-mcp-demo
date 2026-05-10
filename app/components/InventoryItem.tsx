import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/lib/theme";
import { localIsoDate } from "@/lib/local-day";
import type { InventoryItem as InventoryItemType } from "@/lib/types";

interface InventoryItemProps {
  item: InventoryItemType;
}

function InventoryItemRowImpl({ item }: InventoryItemProps) {
  const urgency =
    item.estimatedDaysLeft <= 2 ? "critical" : item.estimatedDaysLeft <= 5 ? "low" : "ok";

  const urgencyConfig = {
    critical: { bg: colors.accent.dangerDim, text: colors.accent.danger, icon: "alert-circle" as const },
    low: { bg: colors.accent.warningDim, text: colors.accent.warning, icon: "warning" as const },
    ok: { bg: colors.accent.successDim, text: colors.accent.success, icon: "checkmark-circle" as const },
  };

  const config = urgencyConfig[urgency];

  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        backgroundColor: colors.surface.card,
        borderRadius: radius.md,
        padding: 12,
        marginBottom: 8,
        borderWidth: 1,
        borderColor: item.isLowStock ? `rgba(248,113,113,0.2)` : colors.border.subtle,
      }}
    >
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={{ fontSize: 14, fontWeight: "600", color: colors.text.primary }}>{item.name}</Text>
          {item.expiryDate && new Date(item.expiryDate) < new Date(localIsoDate()) && (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.accent.dangerDim, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 1 }}>
              <Ionicons name="alert-circle" size={10} color={colors.accent.danger} />
              <Text style={{ fontSize: 10, fontWeight: "700", color: colors.accent.danger }}>Expired</Text>
            </View>
          )}
        </View>
        <Text style={{ fontSize: 12, color: colors.text.secondary, marginTop: 2 }}>
          {item.currentQuantity} {item.unit} remaining
        </Text>
      </View>

      <View style={{ alignItems: "flex-end", gap: 4 }}>
        {/* If the item is past its expiry date, showing "Nd left" is
            contradictory with the "Expired" badge. Hide the days-left chip. */}
        {!(item.expiryDate && new Date(item.expiryDate) < new Date(localIsoDate())) && (
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              backgroundColor: config.bg,
              borderRadius: 6,
              paddingHorizontal: 8,
              paddingVertical: 3,
            }}
          >
            <Ionicons name={config.icon} size={12} color={config.text} />
            <Text style={{ fontSize: 11, fontWeight: "600", color: config.text }}>
              {item.estimatedDaysLeft}d left
            </Text>
          </View>
        )}
        <Text style={{ fontSize: 10, color: colors.text.muted }}>{item.category}</Text>
      </View>
    </View>
  );
}

/** Memoised so the kitchen list doesn't re-render every row when the
 *  parent's sort / filter state changes. */
export const InventoryItemRow = React.memo(InventoryItemRowImpl);
