/**
 * Vitest config — pure unit tests for client-side logic helpers.
 *
 * Component/screen tests would need a React Native testing environment
 * (jest-expo, react-native-testing-library, etc.) which is much heavier.
 * For the Your Kitchen scope we only test the pure helpers + render-time
 * computations that don't depend on RN primitives. UI verification lives
 * in `.maestro/flows/dish_first/your_kitchen_happy_path.yaml`.
 */

import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  test: {
    environment: "node",
    include: ["**/__tests__/**/*.{test,spec}.{ts,tsx}"],
    exclude: ["**/node_modules/**", "**/.expo/**", "**/ios/**", "**/android/**"],
  },
});
