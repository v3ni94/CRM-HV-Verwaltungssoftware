"use client";

import { useTranslations } from "next-intl";

import { ui } from "@/lib/ui";

/** Event the assistant widget listens to (M7-05): opens the chat with the record of the page
 *  as context (the widget reads area and record from the route). */
export const ASSISTANT_OPEN_EVENT = "mhvp:assistant-open";

export function openAssistant(): void {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(ASSISTANT_OPEN_EVENT));
}

/** Reiter "Assistent" am Objekt und am Kontakt (10 Einleitung, M7-05): explains what the
 *  assistant can prepare for this record and opens it. Every action stays a proposal that is
 *  confirmed in the chat (10.3). */
export function AssistantTab({ kind }: { kind: "property" | "contact" }) {
  const t = useTranslations("AiChat.assistantTab");
  const actions = kind === "property" ? ["documentFile", "letter", "ticket", "appointment"] : ["portalInvite", "letter", "note", "documentFile"];
  return (
    <section id="assistent" className={`${ui.card} flex flex-col gap-3`} data-testid="assistant-tab">
      <h2 className="text-sm font-semibold">{t("title")}</h2>
      <p className="text-sm text-muted">{t(kind === "property" ? "introProperty" : "introContact")}</p>
      <ul className="list-disc pl-5 text-sm">
        {actions.map((a) => (
          <li key={a}>{t(`actions.${a}`)}</li>
        ))}
      </ul>
      <p className="text-xs text-muted">{t("proposalNotice")}</p>
      <div>
        <button type="button" className={ui.primary} onClick={openAssistant} data-testid="assistant-open">
          {t("open")}
        </button>
      </div>
    </section>
  );
}
