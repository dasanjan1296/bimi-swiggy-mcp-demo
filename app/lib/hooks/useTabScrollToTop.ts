import { useRef } from "react";
import { useScrollToTop } from "@react-navigation/native";

/**
 * C5 fix: Tap on the active tab scrolls the screen to the top — matches
 * iOS / Twitter / Instagram behaviour. Use this in every tab screen and
 * pass the returned ref to the outermost ScrollView / FlatList.
 *
 * Example:
 *   const scrollRef = useTabScrollToTop();
 *   return <ScrollView ref={scrollRef}>...</ScrollView>
 */
export function useTabScrollToTop<T = any>() {
  const ref = useRef<T>(null);
  useScrollToTop(ref as any);
  return ref;
}
