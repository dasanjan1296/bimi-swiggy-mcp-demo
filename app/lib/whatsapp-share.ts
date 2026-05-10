import { Linking } from "react-native";
import { showAlert } from "./dialogs";

export function shareWithCook(cookPhone: string | undefined, message: string) {
  if (!cookPhone) {
    showAlert("No Phone", "No cook phone number set. Add it in Settings.");
    return;
  }
  const phone = cookPhone.replace(/[^0-9]/g, "");
  const url = `whatsapp://send?phone=${phone}&text=${encodeURIComponent(message)}`;
  Linking.openURL(url).catch(() => {
    Linking.openURL(`https://wa.me/${phone}?text=${encodeURIComponent(message)}`).catch(() => {});
  });
}
