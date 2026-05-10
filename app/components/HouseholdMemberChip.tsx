import React from "react";
import { View, Text, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius } from "@/lib/theme";
import type { HouseholdMember } from "@/lib/types";

interface HouseholdMemberChipProps {
  member: HouseholdMember;
  isActive?: boolean;
  onPress?: () => void;
  showRole?: boolean;
  size?: "sm" | "md" | "lg";
}

const ROLE_LABELS: Record<string, string> = {
  husband: "Husband",
  wife: "Wife",
  mom: "Mom",
  dad: "Dad",
  son: "Son",
  daughter: "Daughter",
  kid: "Kid",
  flatmate: "Flatmate",
};

function HouseholdMemberChipImpl({
  member,
  isActive,
  onPress,
  showRole,
  size = "md",
}: HouseholdMemberChipProps) {
  const sizes = {
    sm: { avatar: 28, font: 11, padding: 6 },
    md: { avatar: 36, font: 13, padding: 8 },
    lg: { avatar: 48, font: 15, padding: 12 },
  };
  const s = sizes[size];

  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={!onPress}
      activeOpacity={0.7}
      hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: s.padding,
        backgroundColor: isActive ? colors.accent.primaryDim : colors.surface.card,
        borderRadius: radius.pill,
        paddingHorizontal: s.padding + 4,
        paddingVertical: s.padding,
        minHeight: 44,
        borderWidth: 1,
        borderColor: isActive ? colors.border.active : colors.border.subtle,
      }}
    >
      <View
        style={{
          width: s.avatar,
          height: s.avatar,
          borderRadius: s.avatar / 2,
          backgroundColor: isActive ? colors.accent.primaryDim : colors.surface.elevated,
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <Ionicons name="person-circle" size={s.avatar * 0.65} color={isActive ? colors.accent.primary : colors.text.secondary} />
      </View>
      <View>
        <Text style={{ fontSize: s.font, fontWeight: "600", color: colors.text.primary }}>
          {member.name}
        </Text>
        {showRole && (
          <Text style={{ fontSize: s.font - 2, color: colors.text.secondary }}>
            {ROLE_LABELS[member.role] || member.role}
          </Text>
        )}
      </View>
    </TouchableOpacity>
  );
}

/** Memoised so member rows in voting / settings / household-setup don't
 *  re-render every time the parent's countdown / expansion state changes. */
export const HouseholdMemberChip = React.memo(HouseholdMemberChipImpl);
