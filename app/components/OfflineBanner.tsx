import { View, Text, Platform, AccessibilityInfo } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useEffect, useRef, useState } from "react";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { colors, spacing, typography } from "@/lib/theme";
import { useReducedMotion } from "@/lib/useReducedMotion";

// Defensive: expo-network's native module isn't linked into the current
// dev client. Wrap the require so a missing module degrades to a no-op
// rather than crashing the entire app surface.
let Network: any = null;
try {
  Network = require("expo-network");
} catch {
  /* leave Network as null; banner just stays hidden */
}

// Native: Network.addNetworkStateListener fires on connectivity changes (no polling).
// Web: navigator.onLine + 'online'/'offline' window events.
// 2-tick hysteresis avoids flapping on flaky networks.

const OFFLINE_HYSTERESIS = 2;

export function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(false);
  const offlineTicks = useRef(0);
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    let mounted = true;

    const apply = (online: boolean) => {
      if (!mounted) return;
      if (!online) {
        offlineTicks.current += 1;
        if (offlineTicks.current >= OFFLINE_HYSTERESIS) setIsOffline(true);
      } else {
        offlineTicks.current = 0;
        setIsOffline(false);
      }
    };

    if (Platform.OS === "web") {
      const update = () => apply((globalThis as any).navigator?.onLine ?? true);
      update();
      const w = (globalThis as any).window;
      w?.addEventListener?.("online", update);
      w?.addEventListener?.("offline", update);
      return () => {
        mounted = false;
        w?.removeEventListener?.("online", update);
        w?.removeEventListener?.("offline", update);
      };
    }

    if (!Network || typeof Network.getNetworkStateAsync !== "function") {
      // Native module not linked — assume online and stay quiet.
      return () => {
        mounted = false;
      };
    }

    Network.getNetworkStateAsync()
      .then((s: any) => apply(s.isConnected !== false && s.isInternetReachable !== false))
      .catch(() => {});

    const sub = Network.addNetworkStateListener?.((s: any) => {
      apply(s.isConnected !== false && s.isInternetReachable !== false);
    });

    return () => {
      mounted = false;
      sub?.remove?.();
    };
  }, []);

  useEffect(() => {
    if (isOffline) {
      AccessibilityInfo.announceForAccessibility?.("You are offline. Changes will sync when connected.");
    }
  }, [isOffline]);

  if (!isOffline) return null;

  const banner = (
    <View
      accessibilityRole={"alert" as any}
      accessibilityLiveRegion="polite"
      accessibilityLabel="You are offline. Changes will sync when connected."
      style={{
        backgroundColor: colors.accent.warningDim,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        paddingVertical: 6,
        paddingHorizontal: spacing.md,
      }}
    >
      <Ionicons name="cloud-offline-outline" size={14} color={colors.accent.warning} />
      <Text style={{ ...typography.tiny, color: colors.accent.warning, fontWeight: "600" }}>
        You're offline — changes will sync when connected
      </Text>
    </View>
  );

  if (reducedMotion) return banner;

  return (
    <Animated.View entering={FadeInUp.duration(220)} exiting={FadeOutUp.duration(180)}>
      {banner}
    </Animated.View>
  );
}
