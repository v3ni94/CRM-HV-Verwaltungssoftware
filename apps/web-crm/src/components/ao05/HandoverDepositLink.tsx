"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatEur } from "@/lib/format";
import { ui } from "@/lib/ui";
import { useBusy } from "@/lib/use-busy";

type Link = {
  protocol_id: string;
  contract_id: string | null;
  deposit_id: string | null;
  deposit_status: string | null;
  deposit_amount_due: string | null;
  protocol_deposit_amount: string | null;
  difference: string | null;
  iban_suffix: string | null;
  contact_id: string | null;
  bank_account_id: string | null;
  bank_account_approval: string | null;
  hints: string[];
  bank_account_created?: boolean | null;
};

/** Kautionsverknüpfung im Übergabeprotokoll (AN19-CRM, GAK-206): `GET` zeigt den Abgleich mit Vertrag
 *  und Freigabe, `POST /handover/protocols/{id}/deposit/link` gibt die Rückzahlungs-IBAN zur Freigabe
 *  an den Kontakt. Es wird nichts gezahlt und die Kaution nicht geändert. */
export function HandoverDepositLink({ base, disabled }: { base: string; disabled: boolean }) {
  const t = useTranslations("Ao05.depositLink");
  const [state, setState] = useState<Link | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const { busy, guard } = useBusy();
  const url = `${base}/deposit/link`;

  useEffect(() => {
    let active = true;
    void (async () => {
      const res = await bff<Link>(url);
      if (!active) return;
      if (res.ok) setState(res.data);
      else setError(res.message);
    })();
    return () => {
      active = false;
    };
  }, [url]);

  const link = guard(async () => {
    setError(null);
    setDone(false);
    const res = await bff<Link>(url, { method: "POST", body: JSON.stringify({}) });
    if (res.ok) {
      setState(res.data);
      setDone(true);
    } else setError(res.message);
  });

  return (
    <section className="flex flex-col gap-2" data-testid="deposit-link">
      <h3 className="text-sm font-medium">{t("title")}</h3>
      <p className={ui.notice}>{t("fourEyes")}</p>
      {state ? (
        <div className="text-sm">
          <p>
            {t("due")}: {state.deposit_amount_due ? formatEur(state.deposit_amount_due) : t("none")}; {t("protocol")}:{" "}
            {state.protocol_deposit_amount ? formatEur(state.protocol_deposit_amount) : t("none")}
            {state.difference ? `; ${t("difference")}: ${formatEur(state.difference)}` : ""}
          </p>
          <p>
            {t("account")}: {state.iban_suffix ? `…${state.iban_suffix}` : t("none")}
            {state.bank_account_approval ? ` (${state.bank_account_approval})` : ""}
          </p>
          {state.hints.length > 0 ? (
            <ul className="list-disc pl-5 text-xs text-muted" data-testid="deposit-hints">
              {state.hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      <div>
        <button type="button" className={ui.button} disabled={busy || disabled} onClick={() => void link()}>
          {t("link")}
        </button>
      </div>
      {done ? <p role="status" className={ui.success}>{t("done")}</p> : null}
      {error ? <p role="alert" className={ui.alert}>{error}</p> : null}
    </section>
  );
}
