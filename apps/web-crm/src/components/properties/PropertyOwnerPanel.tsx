"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CurrentOwner = {
  id: string;
  party_id: string;
  party_name: string;
  contact_id: string | null;
  contact_name: string | null;
  share_percent: string | null;
  valid_from: string;
  valid_to: string | null;
};

type Hit = { id: string; display_name: string };

function dmy(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

function share(value: string | null): string | null {
  if (value == null) return null;
  const n = Number(value);
  return Number.isFinite(n)
    ? `${n.toLocaleString("de-DE", { maximumFractionDigits: 4 })} %`
    : value;
}

/** Eigentümer des Mietverwaltungsobjekts (operator 26.09.2026): ohne Objekteigentümer findet
 *  die Zuordnung keinen Vermieter. Festlegen über POST /properties/{id}/owner mit Kontakt,
 *  Beginn und Anteil; ein bestehender Eigentümer wird nur mit ausdrücklichem Ersetzen beendet.
 *  Bei WEG-Objekten wird das Eigentum je Einheit geführt. */
export function PropertyOwnerPanel({
  propertyId,
  managementType,
  owners,
  canEdit,
}: {
  propertyId: string;
  managementType: string;
  owners: CurrentOwner[];
  canEdit: boolean;
}) {
  const t = useTranslations("Properties.owner");
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [contact, setContact] = useState<Hit | null>(null);
  const [validFrom, setValidFrom] = useState("");
  const [sharePercent, setSharePercent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (managementType !== "rental") {
    return (
      <section className={ui.card} data-testid="property-owner">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        <p className="mt-2 text-sm text-muted">{t("perUnit")}</p>
      </section>
    );
  }

  const replacing = owners.length > 0;
  const shareValid =
    sharePercent.trim() === "" ||
    /^\d{1,3}([.,]\d{1,4})?$/.test(sharePercent.trim());
  const shareNumber = Number(sharePercent.trim().replace(",", "."));
  const shareInRange =
    sharePercent.trim() === "" || (shareNumber > 0 && shareNumber <= 100);
  const dateNeeded = replacing && validFrom === "";
  const valid = contact !== null && shareValid && shareInRange && !dateNeeded;
  const hint =
    contact === null
      ? t("chooseContact")
      : !shareValid || !shareInRange
        ? t("shareInvalid")
        : dateNeeded
          ? t("dateRequired")
          : null;

  const reset = () => {
    setOpen(false);
    setConfirming(false);
    setQuery("");
    setHits([]);
    setContact(null);
    setValidFrom("");
    setSharePercent("");
    setError(null);
  };

  const search = async (q: string) => {
    setQuery(q);
    setContact(null);
    if (q.trim().length < 2) {
      setHits([]);
      return;
    }
    const res = await bff<{ items: Hit[] }>(
      `/api/bff/contacts?q=${encodeURIComponent(q.trim())}&page_size=8`,
    );
    setHits(res.ok ? res.data.items : []);
  };

  const save = async () => {
    if (!contact) return;
    setBusy(true);
    setError(null);
    const body: Record<string, unknown> = { contact_id: contact.id };
    if (validFrom) body.valid_from = validFrom;
    if (sharePercent.trim())
      body.share_percent = sharePercent.trim().replace(",", ".");
    if (replacing) body.replace = true;
    const res = await bff<{ status: string }>(
      `/api/bff/properties/${propertyId}/owner`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    );
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      setConfirming(false);
      return;
    }
    reset();
    router.refresh();
  };

  return (
    <section className={ui.card} data-testid="property-owner">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={ui.subtitle}>{t("title")}</h2>
        {canEdit && !open ? (
          <button
            type="button"
            className={ui.buttonSm}
            onClick={() => setOpen(true)}
          >
            {replacing ? t("replace") : t("set")}
          </button>
        ) : null}
      </div>
      {owners.length === 0 ? (
        <p className="mt-2 text-sm">
          <span className={ui.badgeWarning}>{t("missing")}</span>{" "}
          <span className="text-muted">{t("missingHint")}</span>
        </p>
      ) : (
        <ul className="mt-2 flex flex-col gap-1 text-sm">
          {owners.map((o) => (
            <li key={o.id} className="flex flex-wrap gap-x-3">
              {o.contact_id ? (
                <Link
                  href={`/kontakte/${o.contact_id}`}
                  className="font-medium hover:underline"
                >
                  {o.contact_name ?? o.party_name}
                </Link>
              ) : (
                <span className="font-medium">{o.party_name}</span>
              )}
              <span className="text-muted">
                {t("since", { date: dmy(o.valid_from) })}
              </span>
              {share(o.share_percent) ? (
                <span className="text-muted">
                  {t("share", { share: share(o.share_percent) ?? "" })}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <div
          role="dialog"
          aria-modal="false"
          aria-labelledby="owner-dialog-title"
          className="mt-3 flex flex-col gap-3 border-t border-border pt-3"
          data-testid="owner-dialog"
        >
          <h3 id="owner-dialog-title" className="font-medium">
            {replacing ? t("replace") : t("set")}
          </h3>
          {confirming && contact ? (
            <>
              <p className="text-sm">
                {t(replacing ? "confirmReplace" : "confirmSet", {
                  name: contact.display_name,
                  date: validFrom ? dmy(validFrom) : t("defaultStart"),
                })}
              </p>
              <div className={ui.formActions}>
                <button
                  type="button"
                  className={ui.primary}
                  disabled={busy}
                  onClick={save}
                >
                  {t("confirm")}
                </button>
                <button
                  type="button"
                  className={ui.button}
                  disabled={busy}
                  onClick={() => setConfirming(false)}
                >
                  {t("back")}
                </button>
              </div>
            </>
          ) : (
            <>
              <label className={ui.label}>
                {t("contact")}
                <input
                  className={ui.input}
                  value={contact ? contact.display_name : query}
                  onChange={(e) => search(e.target.value)}
                  placeholder={t("searchPlaceholder")}
                />
              </label>
              {contact === null && hits.length > 0 ? (
                <ul
                  className="flex flex-col gap-1 text-sm"
                  data-testid="owner-hits"
                >
                  {hits.map((h) => (
                    <li key={h.id}>
                      <button
                        type="button"
                        className="hover:underline"
                        onClick={() => {
                          setContact(h);
                          setHits([]);
                        }}
                      >
                        {h.display_name}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              <label className={ui.label}>
                {t("validFrom")}
                <input
                  type="date"
                  className={ui.input}
                  value={validFrom}
                  onChange={(e) => setValidFrom(e.target.value)}
                />
              </label>
              <p className={ui.help}>
                {replacing ? t("validFromReplaceHelp") : t("validFromHelp")}
              </p>
              <label className={ui.label}>
                {t("sharePercent")}
                <input
                  className={ui.input}
                  inputMode="decimal"
                  value={sharePercent}
                  onChange={(e) => setSharePercent(e.target.value)}
                />
              </label>
              {hint ? <p className="text-sm text-muted">{hint}</p> : null}
              <div className={ui.formActions}>
                <button
                  type="button"
                  className={ui.primary}
                  disabled={!valid}
                  onClick={() => setConfirming(true)}
                >
                  {t("next")}
                </button>
                <button type="button" className={ui.button} onClick={reset}>
                  {t("cancel")}
                </button>
              </div>
            </>
          )}
        </div>
      ) : null}
      {error ? (
        <p role="alert" className={`${ui.alert} mt-2`}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
