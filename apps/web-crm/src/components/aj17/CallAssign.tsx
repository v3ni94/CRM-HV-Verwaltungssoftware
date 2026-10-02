"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
type Out = { contact_name: string | null };

/** Anruf einem Kontakt zuordnen (GAI-420): `POST /communication/calls/{id}/assign` (Recht communication:update).
 *  Bei mehrdeutiger Zuordnung werden die Kandidaten als Auswahl angeboten, sonst Eingabe der Kontakt-ID. */
export function CallAssign({
  callId,
  candidates = [],
  canEdit,
}: {
  callId: string;
  candidates?: { id: string; name: string }[];
  canEdit: boolean;
}) {
  const t = useTranslations("Aj17.callAssign");
  const router = useRouter();
  const [contactId, setContactId] = useState(candidates[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!canEdit) return null;
  const assign = async () => {
    if (!UUID.test(contactId.trim())) {
      setError(t("invalid"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await bff<Out>(`/api/bff/communication/calls/${callId}/assign`, { method: "POST", body: JSON.stringify({ contact_id: contactId.trim() }) });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setDone(res.data?.contact_name ?? contactId.trim());
    router.refresh();
  };
  return (
    <div className="mt-1 flex flex-wrap items-end gap-2" data-testid="call-assign">
      {candidates.length > 0 ? (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("label")}</span>
          <select className={ui.input} value={contactId} onChange={(e) => setContactId(e.target.value)}>
            <option value="">{t("choose")}</option>
            {candidates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      ) : (
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("contactId")}</span>
          <input className={ui.input} value={contactId} onChange={(e) => setContactId(e.target.value)} />
        </label>
      )}
      <button type="button" className={ui.buttonSm} disabled={busy} onClick={() => void assign()}>
        {t("submit")}
      </button>
      {done ? <span role="status" className="text-xs text-muted">{t("done", { name: done })}</span> : null}
      {error ? <span role="alert" className={ui.alert}>{error}</span> : null}
    </div>
  );
}
