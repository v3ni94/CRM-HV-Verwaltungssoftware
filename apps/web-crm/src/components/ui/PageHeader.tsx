import Link from "next/link";

export type Breadcrumb = { href?: string; label: string };

/** Consistent page header: eyebrow label, title, optional description and breadcrumb, plus an
 *  action slot on the right. Purely presentational; pages keep their own data logic. */
export function PageHeader({
  eyebrow,
  title,
  description,
  breadcrumb,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  breadcrumb?: Breadcrumb[];
  action?: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 max-w-full flex-col gap-3 border-b border-border-soft pb-5">
      {breadcrumb && breadcrumb.length > 0 ? (
        <nav aria-label="Breadcrumb" className="mhvp-caption flex flex-wrap items-center gap-1 text-subtle">
          {breadcrumb.map((crumb, index) => (
            <span key={`${crumb.label}-${index}`} className="flex items-center gap-1">
              {index > 0 ? <span aria-hidden>/</span> : null}
              {crumb.href ? (
                <Link href={crumb.href} className="hover:text-fg hover:underline">
                  {crumb.label}
                </Link>
              ) : (
                <span>{crumb.label}</span>
              )}
            </span>
          ))}
        </nav>
      ) : null}
      <div className="flex flex-col items-start gap-4 sm:flex-row sm:flex-wrap sm:justify-between">
        <div className="flex min-w-0 max-w-full flex-col gap-1">
          {eyebrow ? <p className="mhvp-label">{eyebrow}</p> : null}
          <h1 className="mhvp-title mhvp-display min-w-0 break-words font-semibold text-fg [overflow-wrap:anywhere]">{title}</h1>
          {description ? <p className="max-w-2xl break-words text-sm text-muted [overflow-wrap:anywhere]">{description}</p> : null}
        </div>
        {action ? <div className="flex w-full shrink-0 items-center gap-2 sm:w-auto">{action}</div> : null}
      </div>
    </div>
  );
}
