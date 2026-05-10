/**
 * Toast — non-blocking inline feedback.
 *
 * Replaces "success-only" showAlert calls (e.g. "Order approved", "Items added")
 * which interrupt the user with a modal that requires an OK tap. Toasts slide
 * in from the top, auto-dismiss after a short window, and can carry a one-tap
 * action (e.g. "Undo").
 *
 * Anti-pattern this fixes: at last count, ~30 places use showAlert() purely
 * to confirm success — every one of those interrupts the user mid-flow.
 *
 * API:
 *
 *   import { toast } from "@/lib/toast";
 *
 *   toast.success("Order approved", "Split across 3 paying members");
 *   toast.info("Items added");
 *   toast.error("Could not save", "Please try again");
 *   toast.show({ type: "success", title: "Vote cast", action: { label: "Undo", onPress: undoFn } });
 *
 * showAlert / showConfirm remain in dialogs.ts for actual decisions
 * (destructive confirms, multi-button choices). Toasts are for "FYI, this
 * happened" — they should NEVER carry a destructive action.
 */

import { create } from "zustand";

export type ToastType = "success" | "info" | "warning" | "error";

export interface ToastAction {
  label: string;
  onPress: () => void;
}

export interface ToastInput {
  type?: ToastType;
  title: string;
  message?: string;
  action?: ToastAction;
  /** ms before auto-dismiss; defaults to 3000 (5000 if action is present). */
  duration?: number;
}

export interface ToastItem extends Required<Omit<ToastInput, "message" | "action">> {
  id: string;
  message?: string;
  action?: ToastAction;
}

interface ToastState {
  queue: ToastItem[];
  show: (input: ToastInput) => string;
  dismiss: (id: string) => void;
  clear: () => void;
}

export const useToastStore = create<ToastState>((set) => ({
  queue: [],
  show: (input) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const item: ToastItem = {
      id,
      type: input.type ?? "info",
      title: input.title,
      message: input.message,
      action: input.action,
      duration: input.duration ?? (input.action ? 5000 : 3000),
    };
    set((s) => ({ queue: [...s.queue, item] }));
    return id;
  },
  dismiss: (id) =>
    set((s) => ({ queue: s.queue.filter((t) => t.id !== id) })),
  clear: () => set({ queue: [] }),
}));

/** Imperative facade — call from anywhere, no hook needed. */
export const toast = {
  show: (input: ToastInput) => useToastStore.getState().show(input),
  success: (title: string, message?: string, action?: ToastAction) =>
    useToastStore.getState().show({ type: "success", title, message, action }),
  info: (title: string, message?: string, action?: ToastAction) =>
    useToastStore.getState().show({ type: "info", title, message, action }),
  warning: (title: string, message?: string, action?: ToastAction) =>
    useToastStore.getState().show({ type: "warning", title, message, action }),
  error: (title: string, message?: string, action?: ToastAction) =>
    useToastStore.getState().show({ type: "error", title, message, action }),
  dismiss: (id: string) => useToastStore.getState().dismiss(id),
  clear: () => useToastStore.getState().clear(),
};
