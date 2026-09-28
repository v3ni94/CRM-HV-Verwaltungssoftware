import { ui } from "@/lib/ui";

export type KeyValueItem = {
  label: React.ReactNode;
  value: React.ReactNode;
  /** Numeric value: tabular figures, right aligned on phones. Overrides the list default. */
  num?: boolean;
  /** `data-testid` of the value cell. */
  testId?: string;
};

export type KeyValueListProps = {
  items: readonly KeyValueItem[];
  /** All values are numeric (amounts, meter readings). */
  num?: boolean;
  className?: string;
  testId?: string;
};

/** Definition list of label and value pairs that never overflows: two columns on phones
 *  (label grows, value hugs the right edge), a fixed 12 rem label column from `sm`. Values
 *  break long words (IBAN, e-mail, file names) instead of pushing the page (M31). No hooks,
 *  usable from server pages. */
export function KeyValueList({ items, num = false, className = "", testId }: KeyValueListProps) {
  return (
    <dl
      className={`grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-sm sm:grid-cols-[12rem_minmax(0,1fr)] ${className}`.trim()}
      data-testid={testId}
    >
      {items.map((item, index) => {
        const numeric = item.num ?? num;
        return (
          <div key={index} className="contents">
            <dt className="min-w-0 break-words text-muted">{item.label}</dt>
            <dd
              className={`min-w-0 break-words text-fg [overflow-wrap:anywhere] ${numeric ? `${ui.num} text-right sm:text-left` : ""}`.trim()}
              data-testid={item.testId}
            >
              {item.value}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
