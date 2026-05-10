/**
 * BottomSheet — gesture-driven bottom-anchored sheet, backed by
 * @gorhom/bottom-sheet. Replaces the previous Modal-based shell so:
 *
 *   - Swipe-down-to-dismiss actually works (the previous decorative drag
 *     handle was non-functional).
 *   - Snap points are spring-driven, not Modal slide animation.
 *   - The component composes natively with the rest of the keyboard /
 *     safe-area / scroll machinery in the app.
 *
 * The public API is unchanged so existing callers (BookingReviewSheet,
 * PlatformPickerModal, SuggestDishSheet, plus the cook-off "More options"
 * sheet on Home) keep working without code changes.
 */

import React, { useCallback, useEffect, useMemo, useRef } from "react";
import { View, Text, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import {
  BottomSheetModal,
  BottomSheetView,
  BottomSheetScrollView,
  BottomSheetBackdrop,
  type BottomSheetBackdropProps,
} from "@gorhom/bottom-sheet";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, spacing, typography, iconSize } from "@/lib/theme";

export interface BottomSheetProps {
  visible: boolean;
  onClose: () => void;
  title?: string;
  subtitle?: string;
  /** When true, hides the drag-handle pill at the top. */
  hideHandle?: boolean;
  /** When true, content is wrapped in a BottomSheetScrollView (always recommended for tall content). */
  scrollable?: boolean;
  /** Disable tap-on-backdrop dismiss. */
  dismissOnBackdrop?: boolean;
  /** Max height as a fraction of the screen (default 0.92). Translates to a snap point. */
  maxHeightFraction?: number;
  /** Optional node rendered to the right of the title — useful for
   *  a small attribution badge / brand mark next to the headline. */
  titleAccessory?: React.ReactNode;
  children: React.ReactNode;
  style?: ViewStyle;
}

export function BottomSheet({
  visible,
  onClose,
  title,
  subtitle,
  hideHandle = false,
  scrollable = false,
  dismissOnBackdrop = true,
  maxHeightFraction = 0.92,
  titleAccessory,
  children,
  style,
}: BottomSheetProps) {
  const sheetRef = useRef<BottomSheetModal>(null);

  // Snap point = `${maxHeightFraction * 100}%` of screen height.
  const snapPoints = useMemo(
    () => [`${Math.round(maxHeightFraction * 100)}%`],
    [maxHeightFraction],
  );

  // Open / close based on the boolean prop. Imperative present/dismiss is
  // necessary because BottomSheetModal is portal-rendered.
  useEffect(() => {
    if (visible) sheetRef.current?.present();
    else sheetRef.current?.dismiss();
  }, [visible]);

  const handleDismiss = useCallback(() => {
    // Triggered when the user swipes down or taps the backdrop. We always
    // notify the parent so its `visible` state can sync.
    onClose();
  }, [onClose]);

  // Single backdrop scrim opacity. Lighter on the light theme (was 0.65
  // when the app was dark) — too dark a scrim looks heavy on a white app.
  const renderBackdrop = useCallback(
    (p: BottomSheetBackdropProps) => (
      <BottomSheetBackdrop
        {...p}
        appearsOnIndex={0}
        disappearsOnIndex={-1}
        opacity={0.45}
        pressBehavior={dismissOnBackdrop ? "close" : "none"}
      />
    ),
    [dismissOnBackdrop],
  );

  const Header = (title || subtitle) ? (
    <View style={{ flexDirection: "row", alignItems: "flex-start", paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: spacing.md, gap: spacing.sm }}>
      <View style={{ flex: 1 }}>
        {title ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <Text style={typography.h2}>{title}</Text>
            {titleAccessory}
          </View>
        ) : null}
        {subtitle && <Text style={{ ...typography.caption, marginTop: 2 }}>{subtitle}</Text>}
      </View>
      <RipplePressable
        onPress={onClose}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel="Close"
        hitSlop={{ top: 12, left: 12, right: 12, bottom: 12 }}
        style={{ width: 32, height: 32, alignItems: "center", justifyContent: "center" }}
      >
        <Ionicons name="close" size={iconSize.lg} color={colors.text.secondary} />
      </RipplePressable>
    </View>
  ) : null;

  const bodyStyle: ViewStyle = {
    padding: spacing.lg,
    paddingTop: title ? 0 : spacing.lg,
    ...style,
  };

  return (
    <BottomSheetModal
      ref={sheetRef}
      snapPoints={snapPoints}
      enablePanDownToClose
      enableDynamicSizing={false}
      onDismiss={handleDismiss}
      handleComponent={hideHandle ? null : undefined}
      handleIndicatorStyle={{ backgroundColor: colors.border.muted, width: 36, height: 4 }}
      backgroundStyle={{
        backgroundColor: colors.surface.base,
        borderTopLeftRadius: radius.xl,
        borderTopRightRadius: radius.xl,
      }}
      backdropComponent={renderBackdrop}
      // Bottom-sheet handles safe-area itself when keyboardBehavior is set.
      keyboardBehavior="interactive"
      keyboardBlurBehavior="restore"
      android_keyboardInputMode="adjustResize"
    >
      {Header}
      {scrollable ? (
        <BottomSheetScrollView contentContainerStyle={bodyStyle} keyboardShouldPersistTaps="handled">
          {children}
        </BottomSheetScrollView>
      ) : (
        <BottomSheetView style={bodyStyle}>{children}</BottomSheetView>
      )}
    </BottomSheetModal>
  );
}
