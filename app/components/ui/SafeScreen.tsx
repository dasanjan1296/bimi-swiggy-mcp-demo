/**
 * SafeScreen — canonical screen wrapper. Replaces the misleadingly-named
 * GradientScreen (which was just a flat View) and the per-screen
 * `paddingTop: 60` magic number.
 *
 * Usage:
 *   <SafeScreen>
 *     <ScreenHeader title="Settings" />
 *     <ScrollView>...</ScrollView>
 *   </SafeScreen>
 *
 *   // For screens whose Stack.Screen renders a header — opt out of top padding:
 *   <SafeScreen edges={["bottom"]}>...</SafeScreen>
 *
 *   // For first-impression / empty surfaces, enable the biophilic blob backdrop:
 *   <SafeScreen ambientBackdrop>...</SafeScreen>
 */

import React from "react";
import { View, ViewStyle, ScrollView, ScrollViewProps } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { colors } from "@/lib/theme";
import { AmbientBackdrop, type AmbientVariant } from "./AmbientBackdrop";

export type SafeEdge = "top" | "bottom" | "left" | "right";

export interface SafeScreenProps {
  children: React.ReactNode;
  /** Which edges to pad. Defaults to ["top", "bottom"]. */
  edges?: SafeEdge[];
  /** When set, mounts AnimatedBlob ambient atmosphere behind content. */
  ambientBackdrop?: boolean | AmbientVariant;
  /** Wrap children in a ScrollView. Pass scroll-view props to customize. */
  scrollable?: boolean;
  scrollViewProps?: Omit<ScrollViewProps, "children">;
  style?: ViewStyle;
  contentStyle?: ViewStyle;
  background?: string;
}

export function SafeScreen({
  children,
  edges = ["top", "bottom"],
  ambientBackdrop = false,
  scrollable = false,
  scrollViewProps,
  style,
  contentStyle,
  background = colors.surface.warm,
}: SafeScreenProps) {
  const insets = useSafeAreaInsets();
  const padding: ViewStyle = {
    paddingTop: edges.includes("top") ? insets.top : 0,
    paddingBottom: edges.includes("bottom") ? insets.bottom : 0,
    paddingLeft: edges.includes("left") ? insets.left : 0,
    paddingRight: edges.includes("right") ? insets.right : 0,
  };

  const ambientVariant: AmbientVariant =
    ambientBackdrop === true ? "default"
      : ambientBackdrop === false ? "none"
      : ambientBackdrop;

  const content = scrollable ? (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={contentStyle}
      keyboardShouldPersistTaps="handled"
      {...scrollViewProps}
    >
      {children}
    </ScrollView>
  ) : (
    <View style={{ flex: 1, ...contentStyle }}>{children}</View>
  );

  return (
    <View style={[{ flex: 1, backgroundColor: background }, padding, style]}>
      {ambientVariant !== "none" && <AmbientBackdrop variant={ambientVariant} />}
      {content}
    </View>
  );
}
