import { ui } from "@/lib/ui";

export type ResponsiveListProps<T> = {
  rows: readonly T[];
  /** Stable key of a row (usually its id). */
  keyOf: (row: T) => string;
  /** Card content of one row, shown below `sm`; usually a `Link` with the main fields in the
   *  order the plan fixes per record type. */
  card: (row: T) => React.ReactNode;
  /** The complete table (`<table className={ui.table}>` with head and body), shown from `sm`
   *  inside a padding free card that scrolls horizontally. */
  table: React.ReactNode;
  /** `data-testid` of the table wrapper; the card list gets `${testId}-cards`, each card
   *  `${testId}-card`. */
  testId: string;
  /** Extra classes of one card (for example `opacity-60` for terminated records). */
  cardClassName?: (row: T) => string;
  /** Extra data attributes of one card (for example `{ "data-status": row.status }`). */
  cardData?: (row: T) => Record<`data-${string}`, string | undefined>;
  /** Rendered instead of cards and table when `rows` is empty (for example an `EmptyState`). */
  empty?: React.ReactNode;
};

/** Cards on phones, table from `sm` (M31, pattern of `PropertyList`). No hooks and no client
 *  directive, so server pages may render it directly; the interactive parts live in the
 *  `card` and `table` nodes the caller passes in. Every data table in the CRM is rendered
 *  through this component, `ui.tableScroll` or `ui.tableCard` (docs/design/README.md). */
export function ResponsiveList<T>({ rows, keyOf, card, table, testId, cardClassName, cardData, empty }: ResponsiveListProps<T>) {
  if (rows.length === 0 && empty !== undefined) return <>{empty}</>;
  return (
    <>
      <ul className={ui.cardsMobile} data-testid={`${testId}-cards`}>
        {rows.map((row) => (
          <li
            key={keyOf(row)}
            className={`${ui.cardLink} ${cardClassName ? cardClassName(row) : ""}`.trim()}
            data-testid={`${testId}-card`}
            {...(cardData ? cardData(row) : {})}
          >
            {card(row)}
          </li>
        ))}
      </ul>
      <div className={`${ui.tableCard} hidden sm:block`} data-testid={testId}>
        {table}
      </div>
    </>
  );
}
