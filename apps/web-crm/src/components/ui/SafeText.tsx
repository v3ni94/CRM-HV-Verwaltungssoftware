import type { ReactNode } from "react";

/** Width-safe text and HTML containers (operator 26.09.2026, ticket #404): long mail lines
 *  (URLs, subjects, tables in HTML mails) must never widen the page. Every container breaks
 *  words anywhere, keeps line breaks, and HTML content scrolls inside its own box. */
export const SAFE_TEXT_CLASS = "min-w-0 max-w-full whitespace-pre-wrap break-words [overflow-wrap:anywhere]";
export const SAFE_LINE_CLASS = "min-w-0 max-w-full break-words [overflow-wrap:anywhere]";
export const SAFE_HTML_CLASS =
  "mhvp-mail-html min-w-0 max-w-full overflow-x-auto break-words [overflow-wrap:anywhere] [&_img]:h-auto [&_img]:max-w-full [&_pre]:whitespace-pre-wrap [&_pre]:break-words [&_table]:max-w-full [&_table]:table-fixed";

/** Plain text (mail bodies, comments, descriptions) with preserved line breaks. */
export function SafeText({ children, className = "", testId }: { children: ReactNode; className?: string; testId?: string }) {
  return (
    <div className={`${SAFE_TEXT_CLASS} ${className}`.trim()} data-testid={testId}>
      {children}
    </div>
  );
}

/** One line of text (subjects, addresses) that wraps instead of overflowing. */
export function SafeLine({ children, className = "", testId }: { children: ReactNode; className?: string; testId?: string }) {
  return (
    <span className={`${SAFE_LINE_CLASS} ${className}`.trim()} data-testid={testId}>
      {children}
    </span>
  );
}

/** Sanitised HTML mail content in a scrolling container with capped table and image widths.
 *  The caller is responsible for passing sanitised markup. */
export function SafeHtml({ html, className = "", testId }: { html: string; className?: string; testId?: string }) {
  return <div className={`${SAFE_HTML_CLASS} ${className}`.trim()} data-testid={testId} dangerouslySetInnerHTML={{ __html: html }} />;
}
