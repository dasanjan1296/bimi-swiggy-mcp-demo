import * as Haptics from "expo-haptics";

export type SemanticHaptic =
  | "selection"
  | "light"
  | "medium"
  | "success"
  | "warning"
  | "error";

export function haptic(type: SemanticHaptic) {
  switch (type) {
    case "selection":
      Haptics.selectionAsync();
      break;
    case "light":
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      break;
    case "medium":
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
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
