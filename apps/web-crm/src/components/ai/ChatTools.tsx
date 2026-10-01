"use client";

import { useTranslations } from "next-intl";

import type { AiToolUse } from "@/lib/ai";

/** Lookups the model asked for in this answer (tool use, GA10-06, rule AI-TOOL-01): tool,
 *  masked search text and number of hits. Denied tools are shown as such. Display only. */
export function ChatTools({ tools }: { tools: AiToolUse[] | undefined | null }) {
  const t = useTranslations("AiChat");
  if (!tools?.length) return null;
  return (
    <div className="mt-2" data-testid="chat-tools">
      <p className="text-xs font-medium text-muted">{t("toolsTitle")}</p>
      <ul className="mt-1 flex flex-col gap-0.5">
        {tools.map((tool, i) => {
          const search = Object.values(tool.arguments ?? {}).join(", ");
          return (
            <li key={`${tool.tool}:${i}`} className="text-xs text-muted">
              <span className="font-medium text-fg">{tool.label}</span>
              {search ? ` „${search}“` : ""}
              {": "}
              {tool.permitted ? t("toolsHits", { count: tool.count }) : t("toolsDenied")}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
