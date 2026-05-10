/**
 * Compat shim — the canonical implementation now lives in
 * `bimi/app/components/patterns/`. Existing imports from
 * `@/components/GuidanceTip` keep resolving via these re-exports.
 *
 * New code should import from `@/components/patterns`:
 *
 *   import { GuidanceTip, HowItWorks, EmptyState } from "@/components/patterns";
 */

export { GuidanceTip } from "./patterns/GuidanceTip";
export type { GuidanceTipProps } from "./patterns/GuidanceTip";

export { HowItWorks } from "./patterns/HowItWorks";
export type { HowItWorksProps, HowItWorksStep } from "./patterns/HowItWorks";

// Backward-compat alias — older callers used the name `EmptyStateGuide`.
// The canonical name is now `EmptyState`.
export { EmptyState as EmptyStateGuide } from "./patterns/EmptyState";
export type { EmptyStateProps } from "./patterns/EmptyState";
