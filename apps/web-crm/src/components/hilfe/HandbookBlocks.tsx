import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import type { HbBlock } from "@/lib/handbook";

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;

/** Chapter links (`name.md`, `name.md#anker`) point to /hilfe, everything else stays plain text. */
function linkTarget(href: string): string | null {
  const m = /^(?:\.\/)?([a-z0-9-]+)\.md(#[\w-]+)?$/.exec(href);
  if (m) return m[1] === "README" ? "/hilfe" : `/hilfe/${m[1]}${m[2] ?? ""}`;
  return href.startsWith("/") && !href.startsWith("//") ? href : null;
}

export function Inline({ text }: { text: string }): ReactNode {
  return text.split(INLINE).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`"))
      return (
        <code key={i} className="rounded bg-surface-muted px-1 text-[0.9em]">
          {part.slice(1, -1)}
        </code>
      );
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      const target = linkTarget(link[2]!);
      return target ? (
        <Link key={i} href={target} className="underline">
          {link[1]}
        </Link>
      ) : (
        <Fragment key={i}>{link[1]}</Fragment>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

export function HandbookBlocks({ blocks }: { blocks: HbBlock[] }) {
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      {blocks.map((b, i) => {
        switch (b.t) {
          case "h":
            return b.level <= 2 ? (
              <h2 key={i} id={b.id} className="mt-6 scroll-mt-20 text-lg font-semibold">
                {b.text}
              </h2>
            ) : (
              <h3 key={i} id={b.id} className="mt-4 scroll-mt-20 text-base font-semibold">
                {b.text}
              </h3>
            );
          case "p":
            return (
              <p key={i}>
                <Inline text={b.text} />
              </p>
            );
          case "quote":
            return (
              <blockquote key={i} className="border-l-2 border-border-soft pl-3 text-muted">
                <Inline text={b.text} />
              </blockquote>
            );
          case "code":
            return (
              <pre key={i} className="overflow-x-auto rounded bg-surface-muted p-3 text-xs">
                {b.text}
              </pre>
            );
          case "ul":
          case "ol": {
            const List = b.t === "ol" ? "ol" : "ul";
            return (
              <List key={i} className={`${b.t === "ol" ? "list-decimal" : "list-disc"} space-y-1 pl-5`}>
                {b.items.map((it, j) => (
                  <li key={j} style={{ marginLeft: `${it.depth * 1.25}rem` }}>
                    <Inline text={it.text} />
                  </li>
                ))}
              </List>
            );
          }
          case "table":
            return (
              <div key={i} className="overflow-x-auto">
                <table className="w-full border-collapse text-left text-xs">
                  <thead>
                    <tr>
                      {b.head.map((h, j) => (
                        <th key={j} className="border-b border-border-soft p-2 font-semibold">
                          <Inline text={h} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j}>
                        {r.map((c, k) => (
                          <td key={k} className="border-b border-border-soft p-2 align-top">
                            <Inline text={c} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
        }
      })}
    </div>
  );
}
