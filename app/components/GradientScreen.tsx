import React from "react";
import { View, type ViewStyle } from "react-native";
import { colors } from "@/lib/theme";

interface GradientScreenProps {
  children: React.ReactNode;
  style?: ViewStyle;
}

export function GradientScreen({ children, style }: GradientScreenProps) {
  return (
    // surface.warm (very light cream) is the global app-screen canvas.
    // Modals + cards stay on surface.base / surface.elevated (white)
    // so they read as lifted surfaces against this softer ambient.
    <View style={[{ flex: 1, backgroundColor: colors.surface.warm }, style]}>
      {children}
    </View>
  );
}
