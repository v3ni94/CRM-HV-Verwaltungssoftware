export type StatusPillVariant = "neutral" | "success" | "warning" | "danger" | "gold";

const variantClass: Record<StatusPillVariant, string> = {
  neutral: "bg-surface text-muted",
  success: "bg-success-bg text-success-fg",
  warning: "bg-warning-bg text-warning-fg",
  danger: "bg-danger-bg text-danger-fg",
  gold: "bg-gold-soft text-fg",
};

/** Soft status pill with a leading dot (CI badge style). Purely presentational; callers map
 *  their own status values to a variant and label. */
export function StatusPill({
  label,
  variant = "neutral",
  className = "",
}: {
  label: string;
  variant?: StatusPillVariant;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${variantClass[variant]} ${className}`}
    >
      <span className="mhvp-dot" aria-hidden="true" />
      {label}
    </span>
  );
}
