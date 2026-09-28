"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";

import { statusDescriptor, type StatusDescriptor, type StatusDomain, type StatusIcon, type StatusTone } from "@/lib/status-labels";

const toneClass: Record<StatusTone, string> = {
  neutral: "bg-muted-bg text-muted-fg",
  info: "bg-info-bg text-info-fg",
  success: "bg-success-bg text-success-fg",
  warning: "bg-warning-bg text-warning-fg",
  danger: "bg-danger-bg text-danger-fg",
};

function Icon({ name }: { name: StatusIcon }) {
  const common = { "aria-hidden": true, viewBox: "0 0 16 16", className: "h-3 w-3 shrink-0", fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "check":
      return <svg {...common}><path d="m3.5 8.5 3 3 6-7" /></svg>;
    case "clock":
      return <svg {...common}><circle cx="8" cy="8" r="5.5" /><path d="M8 5v3.2l2 1.3" /></svg>;
    case "warning":
      return <svg {...common}><path d="M8 2.5 14 13H2Z" /><path d="M8 6.5V9.5M8 11.3v.2" /></svg>;
    case "cross":
      return <svg {...common}><path d="m4.5 4.5 7 7M11.5 4.5l-7 7" /></svg>;
    case "lock":
      return <svg {...common}><rect x="3.5" y="7" width="9" height="6.5" rx="1" /><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" /></svg>;
    case "pen":
      return <svg {...common}><path d="m3 13 1-3.5L10.5 3l2.5 2.5L6.5 12Z" /></svg>;
    case "send":
      return <svg {...common}><path d="M2.5 8 13.5 2.5 10 13.5 7.5 9Z" /></svg>;
    default:
      return <svg {...common} fill="currentColor" stroke="none"><circle cx="8" cy="8" r="3" /></svg>;
  }
}

type Props = {
  /** Domain and status resolved via `lib/status-labels`; alternatively pass a descriptor. */
  domain?: StatusDomain;
  status?: string | null;
  descriptor?: StatusDescriptor;
  /** Overrides for label or explanation, for example a translated text. */
  label?: string;
  explanation?: string;
  className?: string;
};

/**
 * Status chip with icon and plain text (operator decision 27.09.2026, design proposal 7).
 * Colour only accompanies the meaning; an optional explanation opens as a popover on click
 * or Enter and is also available to screen readers via `aria-describedby`.
 */
export function StatusChip({ domain, status, descriptor, label, explanation, className = "" }: Props) {
  const d = descriptor ?? (domain ? statusDescriptor(domain, status) : { label: String(status ?? ""), tone: "neutral" as const, icon: "dot" as const });
  const text = label ?? d.label;
  const hint = explanation ?? d.explanation;
  const id = useId();
  const [open, setOpen] = useState(false);
  const [flip, setFlip] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  const hintRef = useRef<HTMLSpanElement>(null);

  // Keep the popover inside the viewport (M31): anchored left, flipped to the right edge when
  // it would run past the window.
  useLayoutEffect(() => {
    if (!open || !hintRef.current) return;
    try {
      const rect = hintRef.current.getBoundingClientRect();
      setFlip(rect.right > window.innerWidth);
    } catch {
      /* no layout (server or detached node): keep left anchor */
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onDoc(event: MouseEvent) {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const base = `inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${toneClass[d.tone]} ${className}`;
  if (!hint) {
    return (
      <span className={base} data-status={status ?? undefined}>
        <Icon name={d.icon} />
        {text}
      </span>
    );
  }
  return (
    <span ref={wrap} className="relative inline-flex">
      <button
        type="button"
        className={`${base} cursor-help focus:outline-none focus:ring-2 focus:ring-focus`}
        aria-describedby={`${id}-hint`}
        aria-expanded={open}
        data-status={status ?? undefined}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
      >
        <Icon name={d.icon} />
        {text}
      </button>
      <span
        id={`${id}-hint`}
        ref={hintRef}
        role="tooltip"
        data-flip={flip ? "right" : undefined}
        className={`absolute top-full z-20 mt-1 w-64 max-w-[calc(100vw-2rem)] rounded-lg border border-border bg-raised p-2 text-left text-xs font-normal text-fg shadow-lg ${flip ? "right-0" : "left-0"} ${open ? "" : "sr-only"}`}
      >
        {hint}
      </span>
    </span>
  );
}
