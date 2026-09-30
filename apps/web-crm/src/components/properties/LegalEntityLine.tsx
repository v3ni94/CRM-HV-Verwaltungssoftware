import Link from "next/link";

export type LegalEntityLineItem = { id: string; name: string; kindLabel: string };

/** Legal entities of a property as one line in the header (OP-01). Names link to the ledger when known. */
export function LegalEntityLine({
  label,
  entities,
  ledgerHref,
}: {
  label: string;
  entities: LegalEntityLineItem[];
  ledgerHref: string | null;
}) {
  if (!entities.length) return null;
  return (
    <p className="text-sm text-muted" data-testid="legal-entity-line">
      <span>{label}: </span>
      {entities.map((e, i) => (
        <span key={e.id}>
          {i > 0 ? ", " : ""}
          {ledgerHref ? (
            <Link href={ledgerHref} className="underline">
              {e.name}
            </Link>
          ) : (
            e.name
          )}
          {` (${e.kindLabel})`}
        </span>
      ))}
    </p>
  );
}
