import React from "react";
import { View, Text, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/lib/theme";
import type { CookMessage as CookMessageType } from "@/lib/types";

interface CookMessageProps {
  message: CookMessageType;
  onResolveAction?: (actionIdx: number) => void;
  onAddToWishlist?: (description: string) => void;
  onSuggestMeal?: (description: string) => void;
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: true });
}

function CookMessageBubbleImpl({ message, onResolveAction, onAddToWishlist, onSuggestMeal }: CookMessageProps) {
  const isFromCook = message.isFromCook;

  return (
    <View
      style={{
        alignSelf: isFromCook ? "flex-start" : "flex-end",
        maxWidth: "85%",
        marginBottom: 12,
      }}
    >
      <View
        style={{
          backgroundColor: isFromCook ? colors.surface.card : colors.accent.primaryDim,
          borderRadius: radius.lg,
          borderTopLeftRadius: isFromCook ? 4 : radius.lg,
          borderTopRightRadius: isFromCook ? radius.lg : 4,
          padding: 12,
          borderWidth: 1,
          borderColor: isFromCook ? colors.border.subtle : colors.border.active,
        }}
      >
        {message.type === "voice" && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <Ionicons name="mic" size={14} color={colors.accent.primary} />
            <Text style={{ fontSize: 11, fontWeight: "600", color: colors.accent.primary }}>
              Voice Note
            </Text>
          </View>
        )}

        {message.type === "image" && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 }}>
            <Ionicons name="image" size={14} color={colors.accent.info} />
            <Text style={{ fontSize: 11, fontWeight: "600", color: colors.accent.info }}>
              Photo
            </Text>
          </View>
        )}

        {message.originalHindi && isFromCook && (
          <Text style={{ fontSize: 14, color: colors.text.muted, marginBottom: 4, fontStyle: "italic" }}>
            "{message.originalHindi}"
          </Text>
        )}

        <Text style={{ fontSize: 14, color: colors.text.primary, lineHeight: 20 }}>
          {isFromCook ? message.translation || message.content : message.content}
        </Text>

        <Text style={{ fontSize: 10, color: colors.text.muted, marginTop: 4, textAlign: "right" }}>
          {formatTime(message.timestamp)}
        </Text>
      </View>

      {message.actionItems.length > 0 && isFromCook && (
        <View style={{ marginTop: 6, gap: 4 }}>
          {message.actionItems.map((action, idx) => (
            <TouchableOpacity
              key={idx}
              onPress={() => onResolveAction?.(idx)}
              disabled={action.resolved}
              style={{
                flexDirection: "row",
                alignItems: "center",
                gap: 6,
                backgroundColor: action.resolved ? colors.accent.successDim : colors.accent.primaryDim,
                borderRadius: radius.sm,
                paddingHorizontal: 10,
                paddingVertical: 6,
                borderWidth: 1,
                borderColor: action.resolved
                  ? `rgba(52,211,153,0.3)`
                  : colors.border.active,
              }}
            >
              <Ionicons
                name={action.resolved ? "checkmark-circle" : actionIcon(action.type)}
                size={14}
                color={action.resolved ? colors.accent.success : colors.accent.primary}
              />
              <Text
                style={{
                  fontSize: 12,
                  color: action.resolved ? colors.accent.success : colors.text.primary,
                  flex: 1,
                  textDecorationLine: action.resolved ? "line-through" : "none",
                }}
              >
                {action.description}
              </Text>
              {!action.resolved && (action.type === "supply_request" || action.type === "low_stock") && onAddToWishlist && (
                <TouchableOpacity
                  onPress={() => onAddToWishlist(action.description)}
                  hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
                >
                  <Ionicons name="add-circle" size={16} color={colors.accent.success} />
                </TouchableOpacity>
              )}
              {!action.resolved && action.type === "meal_query" && onSuggestMeal && (
                <TouchableOpacity
                  onPress={() => onSuggestMeal(action.description)}
                  hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
                  style={{ flexDirection: "row", alignItems: "center", gap: 3, backgroundColor: colors.accent.successDim, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 }}
                >
                  <Ionicons name="people-outline" size={12} color={colors.accent.success} />
                  <Text style={{ fontSize: 10, fontWeight: "600", color: colors.accent.success }}>Suggest to Family</Text>
                </TouchableOpacity>
              )}
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

/** Memoised — chat lists re-render frequently when new messages stream
 *  in; without memo each prior bubble re-renders on every new message. */
export const CookMessageBubble = React.memo(CookMessageBubbleImpl);

function actionIcon(type: string): keyof typeof Ionicons.glyphMap {
  switch (type) {
    case "supply_request": return "cart-outline";
    case "meal_query": return "restaurant-outline";
    case "low_stock": return "warning-outline";
    case "absence": return "calendar-outline";
    case "prep_note": return "bulb-outline";
    default: return "ellipse-outline";
  }
}
