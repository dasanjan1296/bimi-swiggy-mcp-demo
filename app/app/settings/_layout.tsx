import { Stack } from "expo-router";
import { colors } from "@/lib/theme";

// Each settings sub-route owns its own ScreenHeader so we hide the native one.
// Keeping headerShown false here lets <SafeScreen edges={["top"]}> handle insets uniformly.
export default function SettingsStackLayout() {
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: colors.surface.warm },
      }}
    >
      <Stack.Screen name="cook" />
      <Stack.Screen name="dietary" />
      <Stack.Screen name="auto-rules" />
    </Stack>
  );
}
