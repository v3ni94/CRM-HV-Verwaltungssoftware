"use client";

import { useTranslations } from "next-intl";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, type RefObject } from "react";
import { createPortal } from "react-dom";

import { CloseIcon } from "@/components/shell/icons";
import { ui } from "@/lib/ui";

export type SheetSize = "sm" | "md" | "full";

export type SheetProps = {
  open: boolean;
  /** Called on Escape, scrim tap, the close button and on a route change while open. */
  onClose: () => void;
  title: string;
  /** `sm` and `md`: bottom sheet below `md`, centred card from `md` (max-w-md or max-w-lg).
   *  `full`: whole viewport below `md`, large card (max-w-3xl, 90 dvh) from `md`. */
  size?: SheetSize;
  /** Sticky footer (actions); stays visible while the body scrolls. */
  footer?: React.ReactNode;
  /** Element that receives focus when the sheet opens; default is the close button. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  children: React.ReactNode;
  testId?: string;
  /** No body padding (for example a photo gallery or a signature canvas). */
  flush?: boolean;
};

const FOCUSABLE =
  "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])";

const PANEL_BY_SIZE: Record<SheetSize, string> = {
  sm: "max-h-[100dvh] rounded-t-xl md:max-h-[90dvh] md:max-w-md md:rounded-xl",
  md: "max-h-[100dvh] rounded-t-xl md:max-h-[90dvh] md:max-w-lg md:rounded-xl",
  full: "h-dvh max-h-[100dvh] md:h-auto md:max-h-[90dvh] md:max-w-3xl md:rounded-xl",
};

/**
 * Modal sheet (M31, ADR 0013): a bottom sheet on phones and tablets, a centred card from `md`;
 * `full` covers the whole viewport on small screens. Portal into `document.body`, scrim,
 * body scroll lock, Escape, close on route change, safe area, focus trap with first focus
 * and focus return to the opener, `role="dialog"` with `aria-modal` and `aria-labelledby`.
 * Layout is pure CSS (`md:` variants), so nothing jumps after hydration. Sits at `z-[90]`,
 * above popovers (z-40) and the palette (z-50), below the navigation drawer (z-[99]).
 */
export function Sheet({ open, onClose, title, size = "md", footer, initialFocusRef, children, testId, flush = false }: SheetProps) {
  const t = useTranslations("Ui");
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  // Route key including the query: a query only navigation (`/objekte` to `/objekte?art=sev`)
  // changes the page content as well. `useSearchParams` needs a Suspense boundary only on
  // statically prerendered routes; the signed in (app) routes are dynamic.
  const pathname = usePathname();
  const search = useSearchParams()?.toString() ?? "";
  const route = search ? `${pathname}?${search}` : (pathname ?? "");
  const pathAtOpen = useRef<string | null>(null);

  // Focus: remember the opener, move focus into the panel, restore on close.
  useEffect(() => {
    if (!open) return;
    openerRef.current = (document.activeElement as HTMLElement | null) ?? null;
    const target = initialFocusRef?.current ?? closeRef.current ?? panelRef.current;
    target?.focus();
    return () => {
      const opener = openerRef.current;
      openerRef.current = null;
      if (opener && opener.isConnected && typeof opener.focus === "function") opener.focus();
    };
    // initialFocusRef is a ref object; its identity is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Escape closes.
  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        onCloseRef.current();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  // Body scroll lock while open.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Close on route change (the sheet belongs to the page it was opened on).
  useEffect(() => {
    if (!open) {
      pathAtOpen.current = null;
      return;
    }
    if (pathAtOpen.current === null) {
      pathAtOpen.current = route;
      return;
    }
    if (route !== pathAtOpen.current) onCloseRef.current();
  }, [open, route]);

  function trapTab(e: React.KeyboardEvent) {
    if (e.key !== "Tab" || !panelRef.current) return;
    const nodes = Array.from(panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    if (nodes.length === 0) {
      e.preventDefault();
      panelRef.current.focus();
      return;
    }
    const first = nodes[0]!;
    const last = nodes[nodes.length - 1]!;
    const current = document.activeElement;
    if (e.shiftKey && (current === first || current === panelRef.current)) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && current === last) {
      e.preventDefault();
      first.focus();
    }
  }

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div className="fixed inset-0 z-[90] flex items-end justify-center md:items-center md:p-4" data-testid={testId}>
      <div className={`absolute inset-0 ${ui.scrim}`} aria-hidden="true" onClick={() => onCloseRef.current()} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onKeyDown={trapTab}
        className={`relative flex w-full flex-col bg-raised text-fg shadow-lg outline-none md:border md:border-border ${PANEL_BY_SIZE[size]}`}
        style={{ paddingTop: size === "full" ? "max(0px, env(safe-area-inset-top))" : undefined }}
        data-size={size}
      >
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border-soft px-4 py-2">
          <h2 id={titleId} className="mhvp-h3 min-w-0 truncate font-semibold text-fg">
            {title}
          </h2>
          <button ref={closeRef} type="button" className={ui.iconButton} aria-label={t("close")} onClick={() => onCloseRef.current()}>
            <CloseIcon className="h-5 w-5" />
          </button>
        </div>
        <div
          className={`min-h-0 flex-1 overflow-y-auto ${flush ? "" : "px-4 py-4"}`}
          style={{ paddingBottom: footer ? undefined : "max(1rem, env(safe-area-inset-bottom))" }}
        >
          {children}
        </div>
        {footer ? (
          <div
            className="sticky bottom-0 shrink-0 border-t border-border-soft bg-raised px-4 pt-3"
            style={{ paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
          >
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
