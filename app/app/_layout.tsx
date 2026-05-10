import "../global.css";
import { Stack, useRouter, useSegments, useRootNavigationState } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { QueryClientProvider } from "@tanstack/react-query";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { BottomSheetModalProvider } from "@gorhom/bottom-sheet";
import { useEffect, useState } from "react";
import { AppState } from "react-native";
import { useAuthStore } from "@/lib/auth-store";
import { useHouseholdStore } from "@/lib/store";
import { refreshToday } from "@/lib/today-store";
import { useLiveSync } from "@/lib/use-sync";
import { useReconcileCookBriefs } from "@/lib/cook-brief-tracking";
import { colors } from "@/lib/theme";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { OfflineBanner } from "@/components/OfflineBanner";
import { ToastHost } from "@/components/ui/ToastHost";
import {
  useFonts,
  PlusJakartaSans_400Regular,
  PlusJakartaSans_500Medium,
  PlusJakartaSans_600SemiBold,
  PlusJakartaSans_700Bold,
  PlusJakartaSans_800ExtraBold,
} from "@expo-google-fonts/plus-jakarta-sans";
import * as SplashScreen from "expo-splash-screen";

SplashScreen.preventAutoHideAsync().catch(() => {});

import { queryClient } from "@/lib/query-client";

function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const segments = useSegments();
  const navigationState = useRootNavigationState();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const loadFromStorage = useAuthStore((s) => s.loadFromStorage);
  const isOnboarded = useHouseholdStore((s) => s.isOnboarded);
  const household = useHouseholdStore((s) => s.household);
  const [isReady, setIsReady] = useState(false);

  useLiveSync();

  // Reconcile any open onboarding cook briefs against (a) inbound
  // cook messages observed since the brief was sent, and (b) the 24h
  // follow-up window. Marks replied briefs as resolved (cancelling
  // the scheduled local notification) and surfaces an in-app
  // reminder for any 24h-old brief with no reply. Cheap; fires once
  // on mount.
  useReconcileCookBriefs();

  useEffect(() => {
    loadFromStorage()
      .catch(() => {})
      .finally(async () => {
        // IC-P1-04: in dev mode + with EXPO_PUBLIC_PILOT_FOUNDER_TOKEN set,
        // hydrate the local household with the seeded pilot family so the
        // home greeting reads the real user's name instead of the
        // placeholder "Anjan" from BACHELOR_HOUSEHOLD.
        try {
          const { hydratePilotFamilyIfDemoMode } = await import("@/lib/dev-bypass");
          await hydratePilotFamilyIfDemoMode();
        } catch {
          // Never block boot on the dev-bypass path.
        }
        // Dev-only: auto-login against the seeded pilot phone so Maestro
        // tests hit a real JWT against the backend instead of demo-mode 401s.
        try {
          const { maybeDevAutoLogin } = await import("@/lib/dev-auto-login");
          await maybeDevAutoLogin();
        } catch {
          // noop — never block boot on the auto-login path.
        }
        setIsReady(true);
      });
  }, []);

  useEffect(() => {
    if (!isReady || !navigationState?.key) return;

    const inAuthGroup = segments[0] === "login" || segments[0] === "household-setup" || segments[0] === "join-house";
    // Legal screens are public-by-design — users need to be able to
    // read Privacy Policy / Terms BEFORE creating an account, and
    // app-store reviewers expect the link to work for them too.
    const isLegalRoute = segments[0] === "legal";
    if (!isAuthenticated && !inAuthGroup && !isLegalRoute) {
      router.replace("/login");
    } else if (isAuthenticated && !household && !inAuthGroup && !isLegalRoute) {
      router.replace("/household-setup");
    } else if (isAuthenticated && household && inAuthGroup && segments[0] !== "join-house") {
      router.replace("/(tabs)");
    }
  }, [isAuthenticated, segments, isReady, navigationState?.key, household]);

  if (!isReady) return null;

  return <>{children}</>;
}

export default function RootLayout() {
  const [fontsLoaded] = useFonts({
    PlusJakartaSans_400Regular,
    PlusJakartaSans_500Medium,
    PlusJakartaSans_600SemiBold,
    PlusJakartaSans_700Bold,
    PlusJakartaSans_800ExtraBold,
  });

  useEffect(() => {
    if (fontsLoaded) SplashScreen.hideAsync().catch(() => {});
  }, [fontsLoaded]);

  useEffect(() => {
    // Idempotent: starts the analytics flusher + Sentry once per app boot.
    import("@/lib/analytics").then(({ initAnalytics, track }) => {
      initAnalytics();
      track("app_opened", { source: "root_layout" });
    });
  }, []);

  useEffect(() => {
    // Roll the in-memory `today` over whenever the app comes to the
    // foreground. Mounted at the root layout so it subscribes ONCE
    // per app boot — keeping the listener out of per-screen mount
    // paths to avoid the iOS Simulator ScrollView layout race that
    // killed the previous in-component reactive `useToday()`.
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") refreshToday();
    });
    return () => sub.remove();
  }, []);

  return (
    // GestureHandlerRootView is required by react-native-gesture-handler (used by
    // RipplePressable and @gorhom/bottom-sheet). BottomSheetModalProvider is what
    // <BottomSheet> uses under the hood for gesture-driven modal sheets.
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <QueryClientProvider client={queryClient}>
          <BottomSheetModalProvider>
            <StatusBar style="dark" />
            <ErrorBoundary>
            <AuthGate>
              <OfflineBanner />
              <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.surface.base },
            headerTintColor: colors.text.primary,
            headerTitleStyle: { fontWeight: "700" },
            headerBackTitle: "Back",
            contentStyle: { backgroundColor: colors.surface.base },
          }}
        >
          {/* 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md):
              the deleted screens — instacook*, kitchen, voting,
              approvals, membership, savings, dish-tracking, insights,
              health-dashboard, meal-calendar, prep-timeline,
              preferences, notification-settings, platform-connections,
              webview-cart, smart-cart, feedback, absence-rescue,
              wishlist, membership-unlock — are no longer mounted.
              Insta Cook is retired. Bimi Gold is retired. Multi-platform
              connect is replaced by Swiggy MCP per Loop 5. */}
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen name="login" options={{ title: "Sign In", headerShown: false }} />
          <Stack.Screen name="cook-chat" options={{ title: "Cook Messages" }} />
          <Stack.Screen name="cook-brief" options={{ title: "Today's brief", headerShown: false }} />
          <Stack.Screen name="notifications" options={{ title: "Notifications" }} />
          <Stack.Screen name="household-setup" options={{ title: "Set Up Your Household", presentation: "fullScreenModal", headerShown: false }} />
          <Stack.Screen name="join-house" options={{ title: "Join a House", headerShown: false }} />
          <Stack.Screen name="dish-catalog" options={{ title: "Bimi Recipes", headerShown: false }} />
          <Stack.Screen name="your-kitchen" options={{ title: "Your Kitchen", headerShown: false }} />
          <Stack.Screen name="dish/[slug]" options={{ title: "Dish", headerShown: false }} />
          <Stack.Screen name="dish-cart" options={{ title: "Your cart", headerShown: false }} />
          <Stack.Screen name="guests" options={{ title: "Guests" }} />
          <Stack.Screen name="cook-interview" options={{ title: "Cook Profile Interview" }} />
          <Stack.Screen name="cook-verify" options={{ title: "Verify Cook Profile" }} />
          {/* Settings sub-stack — its own headerless layout. */}
          <Stack.Screen name="settings" options={{ headerShown: false }} />
          {/* Legal — in-app since we don't host a public website yet. */}
          <Stack.Screen name="legal/privacy" options={{ title: "Privacy Policy" }} />
          <Stack.Screen name="legal/terms" options={{ title: "Terms of Service" }} />
          </Stack>
              {/* Toast host floats above every screen + the tab bar; safe-area-aware. */}
              <ToastHost />
            </AuthGate>
            </ErrorBoundary>
          </BottomSheetModalProvider>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
