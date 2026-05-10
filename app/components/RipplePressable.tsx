import React, { useCallback, useRef } from "react";
import { Platform, Pressable, View, StyleSheet, type ViewStyle, type GestureResponderEvent, type AccessibilityRole, type AccessibilityState } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  runOnJS,
} from "react-native-reanimated";
import * as Haptics from "expo-haptics";
import { useReducedMotion } from "@/lib/useReducedMotion";

type HapticType = "light" | "medium" | "heavy" | "selection" | "success" | "warning" | "error";

interface RipplePressableProps {
  onPress?: () => void;
  onLongPress?: () => void;
  style?: ViewStyle;
  haptic?: HapticType;
  rippleColor?: string;
  scaleValue?: number;
  disabled?: boolean;
  children: React.ReactNode;
  accessibilityLabel?: string;
  accessibilityHint?: string;
  accessibilityRole?: AccessibilityRole;
  accessibilityState?: AccessibilityState;
  hitSlop?: number | { top?: number; left?: number; right?: number; bottom?: number };
  testID?: string;
}

const SPRING_PRESS = { damping: 15, stiffness: 300, mass: 0.8 };
const SPRING_RELEASE = { damping: 22, stiffness: 400, mass: 0.6 };

function triggerHaptic(type: HapticType) {
  switch (type) {
    case "light":
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      break;
    case "medium":
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      break;
    case "heavy":
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Heavy);
      break;
    case "selection":
      Haptics.selectionAsync();
      break;
    case "success":
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      break;
    case "warning":
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      break;
    case "error":
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      break;
  }
}

/**
 * iOS-only sub-component for the soft expanding-ripple overlay. Allocates
 * 4 useSharedValues. Extracted out of the parent so Android renders never
 * pay for these allocations — the perf audit flagged ~5 wasted shared
 * values per tap target on Android otherwise (the ripple itself is
 * Android-system-rendered via android_ripple, not via these values).
 */
const IS_IOS = Platform.OS === "ios";

interface IosRippleHandle {
  trigger: (x: number, y: number) => void;
}

const IosRippleOverlay = React.forwardRef<IosRippleHandle, { color: string; reducedMotion: boolean }>(
  function IosRippleOverlay({ color, reducedMotion }, ref) {
    const opacity = useSharedValue(0);
    const scaleSV = useSharedValue(0);
    const x = useSharedValue(0);
    const y = useSharedValue(0);
    React.useImperativeHandle(
      ref,
      () => ({
        trigger: (px: number, py: number) => {
          if (reducedMotion) return;
          x.value = px;
          y.value = py;
          opacity.value = 1;
          scaleSV.value = 0;
          scaleSV.value = withTiming(2.5, { duration: 250 });
          opacity.value = withTiming(0, { duration: 300 });
        },
      }),
      [reducedMotion, x, y, opacity, scaleSV],
    );
    const rippleStyle = useAnimatedStyle(() => ({
      position: "absolute" as const,
      width: 200,
      height: 200,
      borderRadius: 100,
      backgroundColor: color,
      opacity: opacity.value,
      transform: [
        { translateX: x.value - 100 },
        { translateY: y.value - 100 },
        { scale: scaleSV.value },
      ],
    }));
    return (
      <Animated.View style={[StyleSheet.absoluteFill, { pointerEvents: "none" }]}>
        <Animated.View style={rippleStyle} />
      </Animated.View>
    );
  },
);

export function RipplePressable({
  onPress,
  onLongPress,
  style,
  haptic = "light",
  // Neutral press feedback that reads on white. Was a dark-theme amber
  // tint at rgba(240,160,96,0.15).
  rippleColor = "rgba(0,0,0,0.06)",
  scaleValue = 0.97,
  disabled,
  children,
  accessibilityLabel,
  accessibilityHint,
  accessibilityRole,
  accessibilityState,
  hitSlop,
  testID,
}: RipplePressableProps) {
  const reducedMotion = useReducedMotion();
  const scale = useSharedValue(1);
  const containerRef = useRef<View>(null);
  const rippleRef = useRef<IosRippleHandle>(null);

  const animatedScale = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = useCallback(
    (e: GestureResponderEvent) => {
      if (!reducedMotion) {
        scale.value = withSpring(scaleValue, SPRING_PRESS);
      }
      if (IS_IOS && !reducedMotion) {
        rippleRef.current?.trigger(e.nativeEvent.locationX, e.nativeEvent.locationY);
      }
    },
    [scale, scaleValue, reducedMotion],
  );

  const handlePressOut = useCallback(() => {
    if (!reducedMotion) {
      scale.value = withSpring(1, SPRING_RELEASE);
    }
  }, [scale, reducedMotion]);

  const handlePress = useCallback(() => {
    if (haptic) runOnJS(triggerHaptic)(haptic);
    onPress?.();
  }, [haptic, onPress]);

  // The inner Pressable is the actual tap target. When the consumer's
  // `style` (applied to the outer Animated.View) sets an explicit
  // height / flex, the visible wrapper extends past the Pressable's
  // shrink-wrapped bounds, leaving dead tap zones on the unused area
  // (e.g., the lower half of a calendar cell silently not registering).
  // For those cases the Pressable needs `flex: 1` so its tap area
  // matches the wrapper.
  //
  // BUT — applying `flex: 1` unconditionally breaks the opposite case:
  // a "typical button-pattern" consumer that gives no size at all
  // (e.g., the home tab's b-logo `<RipplePressable style={{
  // alignSelf: "flex-start" }}>`). Under New Architecture / Fabric on
  // Android, an unconstrained `flex: 1` Pressable inside a column
  // container expands to fill the column instead of shrink-wrapping
  // around its 44×44 child, which silently pushes every sibling
  // 2,500+ px below the visible viewport (the home screen body went
  // blank because of this). Yoga's older behaviour (shrink-wrap when
  // parent is unconstrained) was the implicit assumption baked into
  // the original "consumers without a fixed height are unaffected"
  // comment; that assumption no longer holds.
  //
  // So: only apply `flex: 1` when the consumer expressed fill intent
  // via the outer style — explicit height / minHeight, or explicit
  // flex / flexGrow / flexBasis. Otherwise let the Pressable
  // shrink-wrap as Yoga always intended for buttons.
  //
  // We also forward the consumer's CONTENT-layout properties
  // (alignItems / justifyContent / flexDirection / gap) to the
  // Pressable. The consumer's style is conceptually "where children
  // sit" — but those props were applied to Animated.View, whose only
  // child is the Pressable, making the alignment effectively a no-op.
  // Forwarding restores the intent: an IconButton with `alignItems:
  // "center"` centres its icon inside the now-tappable inner area.
  const flatStyle = StyleSheet.flatten(style ?? {}) as ViewStyle;
  const consumerWantsFill =
    flatStyle.flex !== undefined ||
    flatStyle.flexGrow !== undefined ||
    flatStyle.flexBasis !== undefined ||
    flatStyle.height !== undefined ||
    flatStyle.minHeight !== undefined;
  const inheritedLayout: ViewStyle = {
    alignItems: flatStyle.alignItems,
    justifyContent: flatStyle.justifyContent,
    flexDirection: flatStyle.flexDirection,
    gap: flatStyle.gap,
    rowGap: flatStyle.rowGap,
    columnGap: flatStyle.columnGap,
  };

  return (
    <Animated.View style={[animatedScale, style]}>
      <Pressable
        ref={containerRef}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        onPress={handlePress}
        onLongPress={onLongPress}
        disabled={disabled}
        accessibilityLabel={accessibilityLabel}
        accessibilityHint={accessibilityHint}
        accessibilityRole={accessibilityRole}
        accessibilityState={accessibilityState}
        hitSlop={hitSlop as any}
        testID={testID}
        android_ripple={!IS_IOS ? { color: rippleColor, borderless: false } : undefined}
        style={[
          { overflow: "hidden" },
          consumerWantsFill && { flex: 1 },
          inheritedLayout,
        ]}
      >
        {children}
        {IS_IOS && (
          <IosRippleOverlay ref={rippleRef} color={rippleColor} reducedMotion={reducedMotion} />
        )}
      </Pressable>
    </Animated.View>
  );
}
