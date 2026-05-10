/**
 * HeaderWithActions — extension of the canonical `<ScreenHeader>` that
 * supports a row of trailing icon-buttons. Used on home (chat + bell),
 * cook chat (translate toggle), and any screen with up to three quick
 * actions in the corner.
 *
 * For non-icon trailing content (links, badges, etc), use `<ScreenHeader>`
 * directly with the `right` slot.
 */

import React from "react";
import { View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { ScreenHeader } from "../ui/ScreenHeader";
import { IconButton } from "../ui/IconButton";
import { spacing } from "@/lib/theme";

export interface HeaderAction {
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  accessibilityLabel: string;
  /** Optional unread/red dot indicator. */
  active?: boolean;
  /** Optional numeric badge. */
  badge?: number;
  testID?: string;
}

export interface HeaderWithActionsProps {
  title: string;
  subtitle?: string;
  back?: boolean;
  onBack?: () => void;
  actions?: HeaderAction[];
  centered?: boolean;
  style?: ViewStyle;
}

export function HeaderWithActions({
  title,
  subtitle,
  back,
  onBack,
  actions = [],
  centered,
  style,
}: HeaderWithActionsProps) {
  const right =
    actions.length > 0 ? (
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        {actions.map((a) => (
          <IconButton
            key={a.icon}
            icon={a.icon}
            onPress={a.onPress}
            accessibilityLabel={a.accessibilityLabel}
            active={a.active}
            badge={a.badge}
          />
        ))}
      </View>
    ) : null;

  return (
    <ScreenHeader
      title={title}
      subtitle={subtitle}
      back={back}
      onBack={onBack}
      right={right}
      centered={centered}
      style={style}
    />
  );
}
