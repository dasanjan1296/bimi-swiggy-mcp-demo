/**
 * App-wide ErrorBoundary.
 *
 * React renders crash the entire app when an error is thrown during render
 * unless something catches it. We wrap the root navigator so a single bad
 * screen takes itself offline (with a recovery CTA) instead of taking the
 * whole app down to a blank screen.
 *
 * Behaviour:
 *   - On error, log to Sentry (best effort — analytics module init is
 *     side-effect-free and idempotent).
 *   - Render a friendly recovery card with a "Try again" button that
 *     resets the boundary's error state.
 *   - Brand voice per .cursor/skills/bimi-app-development/SKILL.md: warm
 *     guardian, never urgent, never blame the user.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <Stack> ... </Stack>
 *   </ErrorBoundary>
 */

import React from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, spacing, typography } from "@/lib/theme";

interface ErrorBoundaryProps {
  children: React.ReactNode;
  /** Optional override of the default fallback UI. Receives the error and
   *  a reset callback. */
  fallback?: (props: { error: Error; reset: () => void }) => React.ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // Best-effort Sentry report. Never throw from here — that would loop
    // back into getDerivedStateFromError forever.
    void (async () => {
      try {
        const Sentry = await import("@sentry/react-native");
        // Pull the topmost component name from the component stack so
        // Sentry groups errors by the screen they originated in instead
        // of by raw stack trace (which differs across builds).
        const topFrame = (info.componentStack ?? "")
          .split("\n")
          .map((l) => l.trim())
          .find((l) => l.startsWith("at ") || l.startsWith("in "));
        const culprit = topFrame
          ?.replace(/^(at|in)\s+/, "")
          .replace(/\s+\(.*$/, "")
          .slice(0, 80);
        Sentry.captureException(error, {
          tags: {
            source: "ErrorBoundary",
            culprit: culprit ?? "unknown",
          },
          fingerprint: ["ErrorBoundary", culprit ?? error.name, error.message],
          extra: { componentStack: info.componentStack },
        });
      } catch {
        // Sentry not installed / no DSN configured — degrade silently.
      }
    })();

    if (typeof __DEV__ !== "undefined" && __DEV__) {
      // Surface in dev for easier debugging.
      // eslint-disable-next-line no-console
      console.error("[ErrorBoundary]", error, info.componentStack);
    }
  }

  reset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    if (this.props.fallback) {
      return <>{this.props.fallback({ error, reset: this.reset })}</>;
    }

    return <DefaultFallback error={error} reset={this.reset} />;
  }
}

function DefaultFallback({
  error,
  reset,
}: {
  error: Error;
  reset: () => void;
}) {
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: colors.surface.base,
        justifyContent: "center",
        alignItems: "center",
        padding: spacing.xl,
      }}
    >
      <ScrollView
        contentContainerStyle={{
          flexGrow: 1,
          justifyContent: "center",
          alignItems: "center",
          gap: spacing.md,
          maxWidth: 360,
          paddingVertical: spacing.xl,
        }}
        showsVerticalScrollIndicator={false}
      >
        <View
          style={{
            width: 72,
            height: 72,
            borderRadius: 36,
            backgroundColor: colors.accent.dangerDim,
            alignItems: "center",
            justifyContent: "center",
            marginBottom: spacing.sm,
          }}
        >
          <Ionicons
            name="alert-circle-outline"
            size={40}
            color={colors.accent.danger}
          />
        </View>

        <Text
          style={{
            ...typography.h2,
            color: colors.text.primary,
            textAlign: "center",
          }}
        >
          Something tripped me up
        </Text>

        <Text
          style={{
            ...typography.body,
            color: colors.text.secondary,
            textAlign: "center",
          }}
        >
          Don't worry — your meal plans, votes and household setup are all
          safe. Tap below and I'll try this screen again.
        </Text>

        <Pressable
          onPress={reset}
          accessibilityRole="button"
          accessibilityLabel="Try again"
          style={({ pressed }) => ({
            marginTop: spacing.md,
            backgroundColor: colors.accent.primary,
            paddingVertical: spacing.md,
            paddingHorizontal: spacing.xl,
            borderRadius: radius.md,
            opacity: pressed ? 0.85 : 1,
          })}
        >
          <Text
            style={{
              ...typography.bodyBold,
              color: colors.text.inverse,
            }}
          >
            Try again
          </Text>
        </Pressable>

        {typeof __DEV__ !== "undefined" && __DEV__ && (
          <View
            style={{
              marginTop: spacing.lg,
              padding: spacing.md,
              borderRadius: radius.sm,
              backgroundColor: colors.surface.elevated,
              borderWidth: 1,
              borderColor: colors.border.subtle,
              maxWidth: "100%",
            }}
          >
            <Text
              style={{
                ...typography.tiny,
                color: colors.text.muted,
                marginBottom: 4,
                textTransform: "uppercase",
                letterSpacing: 1,
              }}
            >
              Dev-only diagnostics
            </Text>
            <Text
              style={{
                ...typography.small,
                color: colors.accent.danger,
                fontFamily: "Courier",
              }}
              selectable
            >
              {error.name}: {error.message}
            </Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}
