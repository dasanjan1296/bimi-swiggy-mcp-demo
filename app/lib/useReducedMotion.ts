import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

let cachedValue: boolean | null = null;

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(cachedValue ?? false);

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then((val) => {
      cachedValue = val;
      setReduced(val);
    });

    const sub = AccessibilityInfo.addEventListener("reduceMotionChanged", (val) => {
      cachedValue = val;
      setReduced(val);
    });

    return () => sub.remove();
  }, []);

  return reduced;
}
