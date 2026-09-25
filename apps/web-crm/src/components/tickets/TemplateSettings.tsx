"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

import { PRIORITIES } from "./TicketForms";

export type TemplateField = { key: string; label: string; kind: "text" | "iban"; required: boolean };
export type Template = {
  id: string;
  category: string;
  title: string;
  checklist: string[];
  default_priority: string;
  sla_hours: number | null;
  required_fields: TemplateField[];
};

type Draft = {
  id: string | null;
  category: string;
  title: string;
  checklist: string;
  default_priority: string;
  sla_hours: string;
  required_fields: TemplateField[];
};

const EMPTY: Draft = {
  id: null,
  category: "",
  title: "",
  checklist: "",
  default_priority: "normal",
  sla_hours: "",
  required_fields: [],
};

/** Schlüssel aus der Beschriftung ableiten (nur a-z, 0-9, _). */
function keyFor(label: string): string {
  return (
    label
      .toLowerCase()
      .replace(/ä/g, "ae")
      .replace(/ö/g, "oe")
      .replace(/ü/g, "ue")
      .replace(/ß/g, "ss")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 40) || "feld"
  );
}


/** Praxisnahe Standard-SLA einer Hausverwaltung (Reaktionszeiten in Stunden). Nach dem
 *  Einfügen frei anpassbar; eine spätere Erweiterung über die KI-Wissensdatenbank ergänzt
 *  Vorlagen nur auf ausdrücklichen Zuruf eines Administrators. */
const RECOMMENDED: {
  category: string;
  title: string;
  checklist: string[];
  default_priority: string;
  sla_hours: number | null;
  required_fields: TemplateField[];
}[] = [
  {
    category: "Notfall",
    title: "Notfall (Rohrbruch, Heizungsausfall, Stromausfall)",
    checklist: [
      "Gefahr eingrenzen: Absperrung/Haupthahn, Notdienst beauftragen",
      "Mieter und betroffene Parteien informieren",
      "Bereitschaft: Reaktion auch außerhalb der Geschäftszeiten (24/7-Notdienstkette)",
      "Versicherungsrelevanz prüfen und Fotos sichern",
      "Folgeauftrag für dauerhafte Instandsetzung anlegen",
    ],
    default_priority: "urgent",
    sla_hours: 4,
    required_fields: [],
  },
  {
    category: "Reparatur",
    title: "Reparatur dringend (Nutzung eingeschränkt)",
    checklist: [
      "Schaden telefonisch verifizieren",
      "Handwerker beauftragen (Rahmenvertrag prüfen)",
      "Termin mit Mieter abstimmen",
      "Erledigung kontrollieren und Rechnung zuordnen",
    ],
    default_priority: "high",
    sla_hours: 24,
    required_fields: [],
  },
  {
    category: "Reparatur",
    title: "Reparaturmeldung (Standard)",
    checklist: [
      "Meldung erfassen und Objekt/Einheit zuordnen",
      "Zuständigkeit klären (Mieter, Eigentümer, GdWE)",
      "Angebot einholen ab Schwellenwert",
      "Auftrag, Terminierung, Abnahme",
    ],
    default_priority: "normal",
    sla_hours: 72,
    required_fields: [],
  },
  {
    category: "Mieteranfrage",
    title: "Allgemeine Mieteranfrage",
    checklist: ["Anliegen prüfen", "Antwort oder Zwischenbescheid senden"],
    default_priority: "normal",
    sla_hours: 48,
    required_fields: [],
  },
  {
    category: "Vermietung",
    title: "Interessent/Besichtigung",
    checklist: [
      "Rückmeldung an Interessenten",
      "Selbstauskunft anfordern",
      "Besichtigung terminieren",
      "Entscheidung und Absagen versenden",
    ],
    default_priority: "high",
    sla_hours: 24,
    required_fields: [],
  },
  {
    category: "Vermietung",
    title: "Kündigung und Wohnungsabnahme",
    checklist: [
      "Kündigungseingang bestätigen und Frist prüfen",
      "Vorabnahme terminieren",
      "Übergabeprotokoll bei Abnahme erstellen",
      "Kaution und Nebenkostenabrechnung vormerken",
      "Neuvermietung anstoßen",
    ],
    default_priority: "normal",
    sla_hours: 48,
    required_fields: [],
  },
  {
    category: "Kaution",
    title: "Kautionsabrechnung",
    checklist: [
      "Abnahmeprotokoll und offene Forderungen prüfen",
      "Einbehalte begründen und belegen",
      "Auszahlung anweisen",
    ],
    default_priority: "normal",
    sla_hours: 336,
    required_fields: [{ key: "iban", label: "IBAN für die Auszahlung", kind: "iban", required: true }],
  },
  {
    category: "Versicherungsfall",
    title: "Versicherungsfall melden",
    checklist: [
      "Schaden dokumentieren (Fotos, Zeugen)",
      "Meldung an Versicherer",
      "Schadennummer erfassen",
      "Regulierung nachhalten",
    ],
    default_priority: "high",
    sla_hours: 24,
    required_fields: [],
  },
  {
    category: "Buchhaltung",
    title: "Zahlungsrückstand/Mahnung",
    checklist: [
      "Kontoauszug und Sollstellung abgleichen",
      "Zahlungserinnerung senden",
      "Mahnstufe dokumentieren",
    ],
    default_priority: "normal",
    sla_hours: 120,
    required_fields: [],
  },
  {
    category: "Eigentümer",
    title: "Eigentümeranfrage (WEG)",
    checklist: ["Anliegen prüfen", "Beschlusslage/Unterlagen sichten", "Antwort senden"],
    default_priority: "normal",
    sla_hours: 72,
    required_fields: [],
  },
  {
    category: "Mieterhöhung",
    title: "Mieterhöhung prüfen und ankündigen",
    checklist: [
      "Mietspiegel/Vergleichsmieten prüfen",
      "Kappungsgrenze und Fristen prüfen (rechtliche Prüfung, kein Automatismus)",
      "Schreiben als Entwurf zur Freigabe vorlegen",
    ],
    default_priority: "low",
    sla_hours: 336,
    required_fields: [],
  },
];

export function TemplateSettings({ templates }: { templates: Template[] }) {
  const t = useTranslations("TicketTemplates");
  const router = useRouter();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const edit = (tpl: Template) =>
    setDraft({
      id: tpl.id,
      category: tpl.category,
      title: tpl.title,
      checklist: tpl.checklist.join("\n"),
      default_priority: tpl.default_priority,
      sla_hours: tpl.sla_hours ? String(tpl.sla_hours) : "",
      required_fields: tpl.required_fields.map((f) => ({ ...f })),
    });

  const save = async () => {
    if (!draft) return;
    setBusy(true);
    setError(null);
    const body = {
      category: draft.category.trim(),
      title: draft.title.trim(),
      checklist: draft.checklist
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
      default_priority: draft.default_priority,
      sla_hours: draft.sla_hours ? Number(draft.sla_hours) : null,
      required_fields: draft.required_fields
        .filter((f) => f.label.trim())
        .map((f) => ({ ...f, key: f.key || keyFor(f.label), label: f.label.trim() })),
    };
    const res = draft.id
      ? await bff(`/api/bff/ticket-templates/${draft.id}`, { method: "PATCH", body: JSON.stringify(body) })
      : await bff("/api/bff/ticket-templates", { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDraft(null);
    router.refresh();
  };

  const insertRecommended = async () => {
    setBusy(true);
    setError(null);
    const existing = new Set(templates.map((tpl) => tpl.title));
    let failed: string | null = null;
    for (const tpl of RECOMMENDED) {
      if (existing.has(tpl.title)) continue;
      const res = await bff("/api/bff/ticket-templates", {
        method: "POST",
        body: JSON.stringify(tpl),
      });
      if (!res.ok) failed = res.message;
    }
    setBusy(false);
    if (failed) setError(failed);
    router.refresh();
  };

  const remove = async (tpl: Template) => {
    if (!window.confirm(t("deleteConfirm", { category: tpl.category }))) return;
    const res = await bff(`/api/bff/ticket-templates/${tpl.id}`, { method: "DELETE" });
    if (!res.ok) setError(res.message);
    else router.refresh();
  };

  const setField = (index: number, patch: Partial<TemplateField>) =>
    setDraft((d) =>
      d
        ? {
            ...d,
            required_fields: d.required_fields.map((f, i) => (i === index ? { ...f, ...patch } : f)),
          }
        : d,
    );

  return (
    <div className="flex flex-col gap-4">
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {templates.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
      <ul className="grid gap-3 md:grid-cols-2">
        {templates.map((tpl) => (
          <li key={tpl.id} className={ui.card} data-testid="ticket-template">
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className={ui.badge}>{tpl.category}</span>
                <h3 className="mt-1 font-medium">{tpl.title}</h3>
              </div>
              <div className="flex shrink-0 gap-2">
                <button type="button" className={ui.button} onClick={() => edit(tpl)}>
                  {t("edit")}
                </button>
                <button type="button" className={ui.button} onClick={() => remove(tpl)}>
                  {t("delete")}
                </button>
              </div>
            </div>
            <p className="mt-2 text-sm text-muted">
              {t("summary", {
                checklist: tpl.checklist.length,
                fields: tpl.required_fields.length,
                sla: tpl.sla_hours ?? 0,
              })}
            </p>
            {tpl.checklist.length ? (
              <ol className="mt-2 list-decimal pl-5 text-sm">
                {tpl.checklist.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ol>
            ) : null}
          </li>
        ))}
      </ul>

      {draft ? (
        <section className={`${ui.card} flex flex-col gap-3`} aria-label={t("formTitle")}>
          <h3 className="font-medium">{draft.id ? t("editTitle") : t("newTitle")}</h3>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("category")}</span>
              <input className={ui.input} value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("titleField")}</span>
              <input className={ui.input} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("priority")}</span>
              <select className={ui.input} value={draft.default_priority} onChange={(e) => setDraft({ ...draft, default_priority: e.target.value })}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {t(`priorities.${p}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("sla")}</span>
              <input className={ui.input} type="number" min={1} max={8760} value={draft.sla_hours} onChange={(e) => setDraft({ ...draft, sla_hours: e.target.value })} />
            </label>
          </div>
          <label className="flex flex-col gap-1">
            <span className={ui.label}>{t("checklist")}</span>
            <textarea className={`${ui.input} min-h-28`} value={draft.checklist} onChange={(e) => setDraft({ ...draft, checklist: e.target.value })} placeholder={t("checklistHint")} />
          </label>
          <fieldset className="flex flex-col gap-2">
            <legend className={ui.label}>{t("fields")}</legend>
            {draft.required_fields.map((f, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <input className={ui.input} placeholder={t("fieldLabel")} value={f.label} onChange={(e) => setField(i, { label: e.target.value, key: keyFor(e.target.value) })} />
                <select className={ui.input} value={f.kind} onChange={(e) => setField(i, { kind: e.target.value as TemplateField["kind"] })}>
                  <option value="text">{t("kindText")}</option>
                  <option value="iban">{t("kindIban")}</option>
                </select>
                <label className="flex items-center gap-1.5 text-sm">
                  <input type="checkbox" checked={f.required} onChange={(e) => setField(i, { required: e.target.checked })} />
                  {t("required")}
                </label>
                <button type="button" className={ui.button} onClick={() => setDraft({ ...draft, required_fields: draft.required_fields.filter((_, j) => j !== i) })}>
                  {t("removeField")}
                </button>
              </div>
            ))}
            <button
              type="button"
              className={`${ui.button} self-start`}
              onClick={() => setDraft({ ...draft, required_fields: [...draft.required_fields, { key: "", label: "", kind: "text", required: true }] })}
            >
              {t("addField")}
            </button>
            <p className="text-xs text-muted">{t("ibanHint")}</p>
          </fieldset>
          <div className="flex gap-2">
            <button type="button" className={ui.primary} disabled={busy || !draft.category.trim() || !draft.title.trim()} onClick={save}>
              {t("save")}
            </button>
            <button type="button" className={ui.button} onClick={() => setDraft(null)}>
              {t("cancel")}
            </button>
          </div>
        </section>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className={ui.primary} onClick={() => setDraft({ ...EMPTY })}>
            {t("new")}
          </button>
          <button type="button" className={ui.button} disabled={busy} onClick={insertRecommended}>
            {t("insertRecommended")}
          </button>
          <span className="text-xs text-muted">{t("recommendedHint")}</span>
        </div>
      )}
    </div>
  );
}
