import type { CSSProperties } from "react";

export type StatusBadgeState = "ok" | "fail";

export interface StatusBadgeProps {
  state: StatusBadgeState;
  label: string;
}

const styles: Record<StatusBadgeState, CSSProperties> = {
  ok: {
    background: "var(--mhvp-color-success-bg)",
    color: "var(--mhvp-color-success-fg)",
  },
  fail: {
    background: "var(--mhvp-color-danger-bg)",
    color: "var(--mhvp-color-danger-fg)",
  },
};

/** Small status pill; text is always passed in so callers keep i18n control. */
export function StatusBadge({ state, label }: StatusBadgeProps) {
  return (
    <span
      role="status"
      data-state={state}
      style={{
        ...styles[state],
        display: "inline-block",
        borderRadius: "var(--mhvp-radius)",
        padding: "0.125rem 0.5rem",
        fontSize: "0.875rem",
        fontWeight: 500,
      }}
    >
      {label}
    </span>
  );
}
