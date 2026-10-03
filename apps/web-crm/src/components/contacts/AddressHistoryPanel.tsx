"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { bff } from "@/lib/bff";
import { formatDate } from "@/lib/format";
import { ui } from "@/lib/ui";

export type HistoryAddress = {
  id: string;
  street: string | null;
  house_number: string | null;
  postal_code: string | null;
  city: string | null;
  is_primary: boolean;
  valid_from: string | null;
  valid_to: string | null;
  superseded_at: string | null;
};
type AddressList = { items: HistoryAddress[]; history_available: boolean; as_of: string | null };

function line(a: HistoryAddress): string {
  return [[a.street, a.house_number].filter(Boolean).join(" "), [a.postal_code, a.city].filter(Boolean).join(" ")]
    .filter(Boolean)
    .join(", ");
}

/** Address history of a contact (AN05, GAJ-610): only with the tenant switch
 *  contacts.address_history. While it is off (default, OPEN_QUESTIONS AM14-01) the API answers
 *  422 MHVP-CONT-0034 and the panel shows a hint instead. With a cut off date it lists the
 *  addresses valid on that day, otherwise every row including closed ones. Read only. */
export function AddressHistoryPanel({ contactId }: { contactId: string }) {
  const t = useTranslations("Contacts.addressHistory");
  const [asOf, setAsOf] = useState("");
  const [data, setData] = useState<AddressList | null>(null);
  const [off, setOff] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const query = asOf ? `as_of=${encodeURIComponent(asOf)}` : "include_history=true";
    void bff<AddressList>(`/api/bff/contacts/${contactId}/addresses?${query}`).then((res) => {
      if (!alive) return;
      if (res.ok) {
        setData(res.data);
        setOff(false);
        setError(null);
      } else if (res.problem?.code === "MHVP-CONT-0034") {
        setOff(true);
      } else {
        setError(res.message);
      }
    });
    return () => {
      alive = false;
    };
  }, [contactId, asOf]);

  return (
    <section className={ui.card} data-testid="address-history">
      <h2 className="mb-1 text-sm font-semibold">{t("title")}</h2>
      {off ? (
        <p className="text-sm text-muted" data-testid="address-history-off">
          {t("off")}
        </p>
      ) : (
        <>
          <label className="mb-2 flex items-center gap-2 text-sm">
            {t("asOf")}
            <input
              type="date"
              className={ui.input}
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
              data-testid="address-history-as-of"
            />
          </label>
          {error ? (
            <p role="alert" className="text-sm text-danger">
              {error}
            </p>
          ) : null}
          {data && data.items.length === 0 ? <p className="text-sm text-muted">{t("empty")}</p> : null}
          {data && data.items.length > 0 ? (
            <ul className="space-y-1 text-sm">
              {data.items.map((a) => (
                <li key={a.id} data-testid="address-history-row">
                  <span className={a.superseded_at ? "text-muted line-through" : ""}>{line(a)}</span>{" "}
                  <span className="text-xs text-muted">
                    {t("range", {
                      from: a.valid_from ? formatDate(a.valid_from) : t("open"),
                      to: a.valid_to ? formatDate(a.valid_to) : t("open"),
                    })}
                    {a.superseded_at ? ` · ${t("closed")}` : a.is_primary ? ` · ${t("primary")}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}
