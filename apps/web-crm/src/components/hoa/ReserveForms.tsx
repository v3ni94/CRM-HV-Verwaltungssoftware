"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ReserveOption = { id: string; name: string };

/** Earmarked reserve of the community (W08, M24-01): name, purpose, optional account. */
export function ReserveCreateForm({ ledgerId }: { ledgerId: string }) {
  const t = useTranslations("HoaReserves");
  const router = useRouter();
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const res = await bff("/api/bff/hoa/reserves", {
      method: "POST",
      body: JSON.stringify({ ledger_id: ledgerId, name: name.trim(), purpose: purpose.trim() || null }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setName("");
    setPurpose("");
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2" data-testid="reserve-create">
      <h3 className="font-medium">{t("create")}</h3>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("name")}</span>
          <input className={ui.input} value={name} onChange={(e) => setName(e.target.value)} minLength={2} required />
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("purpose")}</span>
          <input className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value)} />
        </label>
        <button type="submit" className={ui.button} disabled={busy || name.trim().length < 2}>
          {t("createSubmit")}
        </button>
      </div>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </form>
  );
}

const KINDS = ["withdrawal", "tax", "fee", "interest"] as const;

/** Use of funds, tax, fee or interest of one reserve and statement; evidence is linked later. */
export function ReserveMovementForm({ statementId, reserves }: { statementId: string; reserves: ReserveOption[] }) {
  const t = useTranslations("HoaReserves");
  const router = useRouter();
  const [reserveId, setReserveId] = useState(reserves[0]?.id ?? "");
  const [kind, setKind] = useState<string>("withdrawal");
  const [amount, setAmount] = useState("");
  const [purpose, setPurpose] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/hoa/statements/${statementId}/reserve-movements`, {
      method: "POST",
      body: JSON.stringify({
        reserve_id: reserveId,
        kind,
        amount: amount.replace(",", "."),
        purpose: purpose.trim(),
      }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setAmount("");
    setPurpose("");
    router.refresh();
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-2" data-testid="reserve-movement">
      <h3 className="font-medium">{t("movementTitle")}</h3>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("reserve")}</span>
          <select className={ui.input} value={reserveId} onChange={(e) => setReserveId(e.target.value)}>
            {reserves.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("kind")}</span>
          <select className={ui.input} value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {t(`kinds.${k}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={ui.label}>{t("amount")}</span>
          <input className={ui.input} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </label>
        <label className="flex flex-1 flex-col gap-1">
          <span className={ui.label}>{t("movementPurpose")}</span>
          <input className={ui.input} value={purpose} onChange={(e) => setPurpose(e.target.value)} minLength={3} required />
        </label>
        <button type="submit" className={ui.button} disabled={busy || !reserveId || !amount || purpose.trim().length < 3}>
          {t("movementSubmit")}
        </button>
      </div>
      <p className={ui.help}>{t("movementHint")}</p>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
    </form>
  );
}
