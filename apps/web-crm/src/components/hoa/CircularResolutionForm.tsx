"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { MajorityCheckLine, type MajorityCheck } from "@/components/hoa/MajorityCheckLine";
import { SUBJECT_KINDS } from "@/components/settings/MajorityRulesAdmin";
import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type CircularOwner = { id: string; label: string };
export type CircularBasis = { id: string; number: number | null; decided_on: string; subject: string };

type Vote = { choice: "" | "yes" | "no" | "abstain"; channel: "email" | "portal" | "letter" | "other"; receivedAt: string };
type Result = {
  id: string;
  number: number;
  status: string;
  missing: number;
  late: number;
  tally: { principle: string; yes: string; no: string; abstain: string } | null;
  majority_check: MajorityCheck | null;
};

const CHOICES = ["", "yes", "no", "abstain"] as const;
const CHANNELS = ["email", "portal", "letter", "other"] as const;

/** Umlaufbeschluss (M25-02): text form votes per owner with channel and time of receipt,
 *  admitted majority (unanimous, or simple after an admitting resolution when the tenant switch
 *  is on), voting deadline and evidence file. The API counts and determines the result; the
 *  legal admissibility of a lowered majority is an assessment, not a rule of the system. */
export function CircularResolutionForm({
  legalEntityId,
  owners,
  resolutions,
  lowerMajorityEnabled,
}: {
  legalEntityId: string;
  owners: CircularOwner[];
  resolutions: CircularBasis[];
  lowerMajorityEnabled: boolean;
}) {
  const t = useTranslations("HoaCircular");
  const tk = useTranslations("MajorityRules");
  const router = useRouter();
  const [subject, setSubject] = useState("");
  const [wording, setWording] = useState("");
  const [decidedOn, setDecidedOn] = useState("");
  const [majority, setMajority] = useState<"unanimous" | "simple">("unanimous");
  const [basis, setBasis] = useState("");
  const [subjectKind, setSubjectKind] = useState("other");
  const [deadline, setDeadline] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [votes, setVotes] = useState<Record<string, Vote>>(() =>
    Object.fromEntries(owners.map((o) => [o.id, { choice: "", channel: "email", receivedAt: "" }])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);

  const setVote = (id: string, patch: Partial<Vote>) =>
    setVotes((v) => ({ ...v, [id]: { ...(v[id] ?? { choice: "", channel: "email", receivedAt: "" }), ...patch } }));
  const simple = majority === "simple";
  const valid =
    subject.trim().length >= 3 &&
    wording.trim().length >= 3 &&
    decidedOn !== "" &&
    file !== null &&
    (!simple || (basis !== "" && deadline !== "" && lowerMajorityEnabled));

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    const uploaded = await bff<{ id: string }>("/api/bff/documents", { method: "POST", body: form });
    if (!uploaded.ok) {
      setBusy(false);
      setError(t("errors.upload"));
      return;
    }
    const consents: Record<string, { choice: string; channel: string; received_at: string | null }> = {};
    for (const [id, v] of Object.entries(votes)) {
      if (v.choice) consents[id] = { choice: v.choice, channel: v.channel, received_at: v.receivedAt ? new Date(v.receivedAt).toISOString() : null };
    }
    const res = await bff<Result>("/api/bff/hoa/circular-resolutions", {
      method: "POST",
      body: JSON.stringify({
        legal_entity_id: legalEntityId,
        subject: subject.trim(),
        wording: wording.trim(),
        decided_on: decidedOn,
        evidence_document_id: uploaded.data.id,
        allowed_majority: majority,
        enabling_resolution_id: simple ? basis : null,
        subject_kind: simple ? subjectKind : null,
        vote_deadline_at: deadline ? new Date(deadline).toISOString() : null,
        consents,
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setResult(res.data);
    router.refresh();
  };

  return (
    <div className="flex flex-col gap-3" data-testid="circular-resolution-form">
      <h3 className={ui.title}>{t("title")}</h3>
      <p className={ui.notice}>{t("hint")}</p>
      {!lowerMajorityEnabled ? <p className={ui.help}>{t("disabled")}</p> : null}
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("subject")}</span>
          <input className={ui.input} value={subject} onChange={(e) => setSubject(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("decidedOn")}</span>
          <input className={ui.input} type="date" value={decidedOn} onChange={(e) => setDecidedOn(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className={ui.label}>{t("wording")}</span>
          <textarea className={ui.input} rows={3} value={wording} onChange={(e) => setWording(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("allowedMajority")}</span>
          <select className={ui.input} value={majority} onChange={(e) => setMajority(e.target.value as "unanimous" | "simple")}>
            <option value="unanimous">{t("majority.unanimous")}</option>
            <option value="simple" disabled={!lowerMajorityEnabled}>
              {t("majority.simple")}
            </option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("voteDeadline")}</span>
          <input className={ui.input} type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} required={simple} />
        </label>
        {simple ? (
          <>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("enablingResolution")}</span>
              <select className={ui.input} value={basis} onChange={(e) => setBasis(e.target.value)} required>
                <option value="">{t("enablingNone")}</option>
                {resolutions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.number !== null ? `Nr. ${r.number} · ` : ""}
                    {r.decided_on} · {r.subject}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("subjectKind")}</span>
              <select className={ui.input} value={subjectKind} onChange={(e) => setSubjectKind(e.target.value)}>
                {SUBJECT_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {tk(`subjectKinds.${k}`)}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        <label className="flex flex-col gap-1 sm:col-span-2">
          <span className={ui.label}>{t("evidence")}</span>
          <input className={ui.input} type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
      </div>
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <caption className="text-left text-xs font-medium text-muted">{t("votes")}</caption>
          <thead>
            <tr>
              <th>{t("owner")}</th>
              <th>{t("choice")}</th>
              <th>{t("channel")}</th>
              <th>{t("receivedAt")}</th>
            </tr>
          </thead>
          <tbody>
            {owners.map((o) => (
              <tr key={o.id}>
                <td>{o.label}</td>
                <td>
                  <select aria-label={`${t("choice")} ${o.label}`} className={ui.input} value={votes[o.id]?.choice ?? ""} onChange={(e) => setVote(o.id, { choice: e.target.value as Vote["choice"] })}>
                    {CHOICES.map((c) => (
                      <option key={c} value={c}>
                        {t(`choices.${c || "none"}`)}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <select className={ui.input} value={votes[o.id]?.channel ?? "email"} onChange={(e) => setVote(o.id, { channel: e.target.value as Vote["channel"] })}>
                    {CHANNELS.map((c) => (
                      <option key={c} value={c}>
                        {t(`channels.${c}`)}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input className={ui.input} type="datetime-local" value={votes[o.id]?.receivedAt ?? ""} onChange={(e) => setVote(o.id, { receivedAt: e.target.value })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={ui.formActions}>
        <button type="button" className={ui.button} onClick={submit} disabled={busy || !valid}>
          {t("submit")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {result ? (
        <div className={ui.success} data-testid="circular-result">
          <p>{t("result", { status: result.status === "positive" || result.status === "negative" ? t(`statuses.${result.status}`) : result.status, number: result.number })}</p>
          {result.tally ? (
            <p>
              {t("resultTally", {
                principle: ["head", "mea", "unit"].includes(result.tally.principle) ? t(`principles.${result.tally.principle}`) : result.tally.principle,
                yes: result.tally.yes,
                no: result.tally.no,
                abstain: result.tally.abstain,
                late: result.late,
              })}
            </p>
          ) : null}
          {result.majority_check ? <MajorityCheckLine check={result.majority_check} /> : null}
        </div>
      ) : null}
    </div>
  );
}
