"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

type Member = {
  contract_id: string;
  unit_number: string | null;
  party_name: string | null;
  present: boolean;
  proxy: boolean;
  votes: Record<string, string>;
};
type Item = { id: string; position: number; resolution: unknown };

/** Attendance and votes per owner (M25). Proxies need text form evidence and are recorded via
 *  the API with the document; one vote per contract and agenda item, no change after casting. */
export function MemberVoting({
  meetingId,
  status,
  members,
  agenda,
}: {
  meetingId: string;
  status: string;
  members: Member[];
  agenda: Item[];
}) {
  const t = useTranslations("HoaWork");
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const post = async (path: string, body: unknown) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/${path}`, { method: "POST", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) router.refresh();
    else setError(res.message);
  };
  const open = status === "invited" || status === "held";
  const openItems = agenda.filter((a) => !a.resolution);
  return (
    <section className="flex flex-col gap-2">
      <h2 className="font-medium">{t("attendance")}</h2>
      <table className="w-full border-collapse text-sm">
        <thead className="border-b border-border text-left text-xs text-muted">
          <tr>
            <th className="py-1.5 pr-3 font-medium">{t("unit")}</th>
            <th className="py-1.5 pr-3 font-medium">{t("owner")}</th>
            <th className="py-1.5 pr-3 font-medium">{t("presence")}</th>
            {openItems.map((a) => (
              <th key={a.id} className="py-1.5 pr-3 font-medium">
                TOP {a.position}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {members.map((m) => {
            const represented = m.present || m.proxy;
            return (
              <tr key={m.contract_id} className="border-b border-border">
                <td className="py-1.5 pr-3">{m.unit_number}</td>
                <td className="py-1.5 pr-3">{m.party_name}</td>
                <td className="py-1.5 pr-3">
                  {m.proxy ? t("byProxy") : m.present ? t("present") : open ? (
                    <button
                      type="button"
                      className={ui.button}
                      disabled={busy}
                      onClick={() => post(`meetings/${meetingId}/attendance`, { contract_id: m.contract_id, present: true })}
                    >
                      {t("markPresent")}
                    </button>
                  ) : (
                    t("absent")
                  )}
                </td>
                {openItems.map((a) => {
                  const cast = m.votes[a.id];
                  return (
                    <td key={a.id} className="py-1.5 pr-3">
                      {cast ? (
                        t(`choice.${cast}`)
                      ) : represented && status === "held" ? (
                        <span className="flex gap-1">
                          {(["yes", "no", "abstain"] as const).map((c) => (
                            <button
                              key={c}
                              type="button"
                              className={ui.button}
                              disabled={busy}
                              aria-label={`${m.unit_number ?? ""} TOP ${a.position} ${t(`choice.${c}`)}`}
                              onClick={() => post(`agenda/${a.id}/votes`, { contract_id: m.contract_id, choice: c })}
                            >
                              {t(`choiceShort.${c}`)}
                            </button>
                          ))}
                        </span>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </section>
  );
}
