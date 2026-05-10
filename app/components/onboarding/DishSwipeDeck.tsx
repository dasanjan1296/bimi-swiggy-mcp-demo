/**
 * DishSwipeDeck — Tinder-style stack of dish photo cards used in step 6
 * (household taste seed). Three verdicts:
 *
 *   • swipe right          → loved
 *   • swipe left           → disliked
 *   • swipe up (or "Like") → liked (the "I'd eat it but I won't fight
 *                            for it" middle bucket — important because
 *                            without it, every "yes" is a "love" and the
 *                            ranking signal collapses)
 *
 * The deck advances exactly one card per swipe, with momentum-decay
 * animation. We render two cards at a time (top + the one underneath,
 * scaled 0.96) so the next photo is already loaded before the user
 * completes the swipe — no flash of empty card.
 *
 * Reduced-motion users get tap-only mode: three buttons under the card
 * (Skip / Like / Love) with no swipe gesture and no spring animation.
 *
 * Why use gesture-handler + reanimated instead of PanResponder: the app
 * already depends on both (used by RipplePressable and the Wheel of
 * Meals), and gesture-handler's swipe physics are dramatically smoother
 * inside scroll surfaces.
 */

import React, { useCallback, useState } from "react";
import { View, Text, Image, Dimensions } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import {
  Gesture,
  GestureDetector,
  GestureHandlerRootView,
} from "react-native-gesture-handler";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
  runOnJS,
  interpolate,
  Extrapolation,
} from "react-native-reanimated";
import { Button } from "../ui";
import { colors, radius, spacing, typography, iconSize } from "@/lib/theme";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { getDishImage } from "@/lib/dish-images";
import type { OnboardingDish } from "@/lib/onboarding-data";

export type SwipeVerdict = "loved" | "liked" | "disliked";

export interface DishSwipeDeckProps {
  dishes: OnboardingDish[];
  onVerdict: (slug: string, verdict: SwipeVerdict) => void;
  /** Called when the deck is exhausted. */
  onDeckEmpty: () => void;
}

const SCREEN_W = Dimensions.get("window").width;
const SWIPE_X_THRESHOLD = SCREEN_W * 0.25;
const SWIPE_Y_THRESHOLD = 110;

export function DishSwipeDeck({ dishes, onVerdict, onDeckEmpty }: DishSwipeDeckProps) {
  const [index, setIndex] = useState(0);
  const reduced = useReducedMotion();

  const tx = useSharedValue(0);
  const ty = useSharedValue(0);

  const advance = useCallback(
    (slug: string, verdict: SwipeVerdict) => {
      onVerdict(slug, verdict);
      const next = index + 1;
      if (next >= dishes.length) {
        onDeckEmpty();
      }
      setIndex(next);
      tx.value = 0;
      ty.value = 0;
    },
    [index, dishes.length, onVerdict, onDeckEmpty, tx, ty],
  );

  const top = dishes[index];
  const beneath = dishes[index + 1];

  const topCardStyle = useAnimatedStyle(() => {
    const rotate = interpolate(tx.value, [-SCREEN_W, 0, SCREEN_W], [-15, 0, 15], Extrapolation.CLAMP);
    return {
      transform: [
        { translateX: tx.value },
        { translateY: ty.value },
        { rotate: `${rotate}deg` },
      ],
    };
  });

  const beneathCardStyle = useAnimatedStyle(() => {
    const progress = Math.min(1, Math.abs(tx.value) / SWIPE_X_THRESHOLD + Math.abs(ty.value) / SWIPE_Y_THRESHOLD);
    const scale = interpolate(progress, [0, 1], [0.96, 1], Extrapolation.CLAMP);
    return { transform: [{ scale }] };
  });

  const overlayStyle = useAnimatedStyle(() => {
    const lovedOpacity  = interpolate(tx.value, [0, SWIPE_X_THRESHOLD],  [0, 1], Extrapolation.CLAMP);
    const dislikeOpacity = interpolate(tx.value, [-SWIPE_X_THRESHOLD, 0], [1, 0], Extrapolation.CLAMP);
    const likeOpacity   = interpolate(ty.value, [-SWIPE_Y_THRESHOLD, 0], [1, 0], Extrapolation.CLAMP);
    return {
      opacity: Math.max(lovedOpacity, dislikeOpacity, likeOpacity),
    };
  });

  const overlayLabel = useAnimatedStyle(() => {
    const isLove = tx.value > Math.abs(ty.value);
    const isDislike = tx.value < 0 && Math.abs(tx.value) > Math.abs(ty.value);
    const color = isLove
      ? colors.accent.success
      : isDislike
        ? colors.accent.danger
        : colors.accent.info;
    return { borderColor: color };
  });

  const pan = Gesture.Pan()
    .enabled(!reduced)
    .onUpdate((e) => {
      tx.value = e.translationX;
      ty.value = Math.min(0, e.translationY);
    })
    .onEnd((e) => {
      "worklet";
      if (!top) return;
      const goRight = e.translationX > SWIPE_X_THRESHOLD;
      const goLeft = e.translationX < -SWIPE_X_THRESHOLD;
      const goUp = e.translationY < -SWIPE_Y_THRESHOLD;
      if (goRight) {
        tx.value = withTiming(SCREEN_W * 1.5, { duration: 220 });
        ty.value = withTiming(ty.value, { duration: 220 });
        runOnJS(advance)(top.slug, "loved");
      } else if (goLeft) {
        tx.value = withTiming(-SCREEN_W * 1.5, { duration: 220 });
        ty.value = withTiming(ty.value, { duration: 220 });
        runOnJS(advance)(top.slug, "disliked");
      } else if (goUp) {
        ty.value = withTiming(-SWIPE_Y_THRESHOLD * 3, { duration: 220 });
        tx.value = withTiming(tx.value, { duration: 220 });
        runOnJS(advance)(top.slug, "liked");
      } else {
        tx.value = withSpring(0, { damping: 18, stiffness: 200 });
        ty.value = withSpring(0, { damping: 18, stiffness: 200 });
      }
    });

  if (!top) {
    return (
      <View
        style={{
          height: 360,
          alignItems: "center",
          justifyContent: "center",
          gap: spacing.md,
          backgroundColor: colors.surface.card,
          borderRadius: radius.xl,
        }}
      >
        <Ionicons name="checkmark-circle" size={iconSize.xxl} color={colors.accent.success} />
        <Text style={typography.bodyBold}>That's enough — Bimi has your taste.</Text>
      </View>
    );
  }

  return (
    <GestureHandlerRootView>
      <View style={{ gap: spacing.lg }}>
        {/* Card stack */}
        <View style={{ height: 380, alignItems: "center", justifyContent: "center" }}>
          {beneath && (
            <Animated.View
              style={[{ position: "absolute" }, beneathCardStyle]}
              accessibilityElementsHidden
              importantForAccessibility="no-hide-descendants"
            >
              <DishCard dish={beneath} />
            </Animated.View>
          )}

          <GestureDetector gesture={pan}>
            <Animated.View
              style={topCardStyle}
              accessibilityRole="image"
              accessibilityLabel={`${top.name}. ${top.blurb}. Swipe right to love, left to skip, up to like.`}
            >
              <DishCard dish={top}>
                <Animated.View
                  style={[
                    {
                      position: "absolute",
                      top: spacing.lg,
                      left: spacing.lg,
                      right: spacing.lg,
                      borderWidth: 4,
                      borderRadius: radius.md,
                      paddingVertical: spacing.sm,
                      alignItems: "center",
                    },
                    overlayStyle,
                    overlayLabel,
                  ]}
                  pointerEvents="none"
                >
                  <Text style={{ ...typography.h2, color: colors.text.primary }}>
                    {/* Empty: the colored ring is the signal; a hard string here would
                        race a frame behind the gesture and look broken. */}
                    {""}
                  </Text>
                </Animated.View>
              </DishCard>
            </Animated.View>
          </GestureDetector>
        </View>

        {/* Tap-only fallback row — accessible to everyone, primary path
            for reduced-motion users. The buttons fire the same
            `advance()` so the deck behaves identically. */}
        <View style={{ flexDirection: "row", gap: spacing.sm, justifyContent: "center" }}>
          <Button
            variant="secondary"
            size="md"
            leadingIcon="close"
            onPress={() => advance(top.slug, "disliked")}
          >
            Skip
          </Button>
          <Button
            variant="secondary"
            size="md"
            leadingIcon="thumbs-up-outline"
            onPress={() => advance(top.slug, "liked")}
          >
            Like
          </Button>
          <Button
            variant="primary"
            size="md"
            leadingIcon="heart"
            onPress={() => advance(top.slug, "loved")}
          >
            Love
          </Button>
        </View>

        <View style={{ alignItems: "center" }}>
          <Text style={typography.tiny}>
            {index + 1} of {dishes.length}
          </Text>
        </View>
      </View>
    </GestureHandlerRootView>
  );
}

function DishCard({ dish, children }: { dish: OnboardingDish; children?: React.ReactNode }) {
  const img = getDishImage(dish.slug);
  const W = Math.min(SCREEN_W - spacing.xl * 2, 340);
  const H = 380;
  return (
    <View
      style={{
        width: W,
        height: H,
        borderRadius: radius.xl,
        backgroundColor: colors.surface.card,
        overflow: "hidden",
        borderWidth: 1,
        borderColor: colors.border.subtle,
      }}
    >
      {img ? (
        <Image
          source={img}
          resizeMode="cover"
          style={{ width: "100%", height: H - 86 }}
          accessible={false}
          accessibilityIgnoresInvertColors
        />
      ) : (
        <View
          style={{
            width: "100%",
            height: H - 86,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Ionicons name="restaurant" size={iconSize.xxl} color={colors.text.muted} />
        </View>
      )}

      <View style={{ padding: spacing.md, gap: 2 }}>
        <Text style={typography.h3} numberOfLines={1}>{dish.name}</Text>
        <Text style={typography.small} numberOfLines={1}>
          {dish.blurb} · {dish.isVeg ? "Veg" : "Non-veg"}
        </Text>
      </View>

      {children}
    </View>
  );
}
