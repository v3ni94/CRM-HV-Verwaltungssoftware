/** Bottom padding a page adds to its content so the last rows stay reachable above a
 *  `BottomBar` (never `h-screen` under a bar). */
export const BOTTOM_BAR_SPACE = "pb-24";

export type BottomBarProps = {
  children: React.ReactNode;
  className?: string;
  testId?: string;
  /** Accessible name of the bar (`role="toolbar"`); optional, the children carry their own. */
  label?: string;
};

/** Viewport fixed action bar at the bottom (M31): full width on phones and tablets, starting
 *  right of the icon rail from `lg` and of the full rail from `xl` (a manual rail mode moves
 *  the edge via `data-rail` on `html`, see base.css). Right padding of 5.5 rem keeps the corner
 *  of the AI launcher free, the bottom padding honours the home indicator. `z-30`, level with
 *  the header. For an in page sticky row inside a form use `ui.bottomBar` instead. No hooks. */
export function BottomBar({ children, className = "", testId, label }: BottomBarProps) {
  return (
    <div
      role={label ? "toolbar" : undefined}
      aria-label={label}
      data-testid={testId}
      className={`mhvp-bottom-bar fixed inset-x-0 bottom-0 z-30 flex flex-wrap items-center gap-2 border-t border-border-soft bg-raised px-4 pt-2 pr-[5.5rem] lg:left-[4.5rem] xl:left-64 ${className}`.trim()}
      style={{ paddingBottom: "max(0.5rem, env(safe-area-inset-bottom))" }}
    >
      {children}
    </div>
  );
}
