import React, { useEffect } from "react";
import { View } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  Easing,
} from "react-native-reanimated";
import { useReducedMotion } from "@/lib/useReducedMotion";

interface AnimatedDotProps {
  color: string;
  size?: number;
  speed?: number;
}

export function AnimatedDot({ color, size = 8, speed = 2000 }: AnimatedDotProps) {
  const reduced = useReducedMotion();
  const opacity = useSharedValue(reduced ? 1 : 0.4);

  useEffect(() => {
    if (reduced) {
      opacity.value = 1;
      return;
    }
    opacity.value = withRepeat(
      withTiming(1, { duration: speed, easing: Easing.inOut(Easing.ease) }),
      -1,
      true,
    );
  }, [opacity, speed, reduced]);

  const animStyle = useAnimatedStyle(() => ({
    width: size,
    height: size,
    borderRadius: size / 2,
    backgroundColor: color,
    opacity: opacity.value,
  }));

  if (reduced) {
    return (
      <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: color }} />
    );
  }

  return <Animated.View style={animStyle} />;
}
