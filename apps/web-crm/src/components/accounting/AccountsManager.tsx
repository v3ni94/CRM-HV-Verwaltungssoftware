"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

export type ManagedAccount = {
  id: string;
  number: string;
  name: string;
  category: string;
  statement_kind?: string;
  type: string;
  vat_option: string;
  relevant_for_cash_report: boolean;
  visible: boolean;
  active: boolean;
  booking_texts?: string[];
  is_system: boolean;
};

const CATEGORIES = ["bank", "cash", "reserve", "loan", "technical", "revenue", "cost", "transit", "tax"] as const;
const TYPES = ["asset", "liability", "income", "expense"] as const;
const VAT = ["none", "full", "reduced"] as const;

type AllocationOut = { items: { allocation_key_id: string; code: string; name: string; share_percent: string }[]; total_percent: string };

/** SA-08: Art der Abrechnung je Konto und Mehrschlüsselverteilung (nur Anzeige, Pflege über die API). */
function AllocationCell({ ledgerId, account }: { ledgerId: string; account: ManagedAccount }) {
  const t = useTranslations("Bookkeeping");
  const [data, setData] = useState<AllocationOut | null>(null);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toggle = async () => {
    if (open) return setOpen(false);
    setOpen(true);
    if (data) return;
    setLoading(true);
    const res = await bff<AllocationOut>(`/api/bff/accounting/ledgers/${ledgerId}/accounts/${account.id}/allocations`);
    setLoading(false);
    if (res.ok) setData(res.data);
    else setError(res.message);
  };
  const kind = account.statement_kind ?? "none";
  return (
    <div className="flex flex-col gap-1">
      <span>{t(`accounts.statementKinds.${kind}`)}</span>
      {account.category === "cost" ? (
        <button type="button" className={ui.buttonSm} onClick={() => void toggle()}>
          {open ? t("accounts.allocationHide") : t("accounts.allocationShow")}
        </button>
      ) : null}
      {open ? (
        <div className="text-sm">
          {loading ? <span>{t("accounts.allocationLoading")}</span> : null}
          {error ? (
            <p role="alert" className={ui.error}>
              {error}
            </p>
          ) : null}
          {data && data.items.length === 0 ? <span>{t("accounts.allocationNone")}</span> : null}
          {data && data.items.length > 0 ? (
            <ul>
              {data.items.map((i) => (
                <li key={i.allocation_key_id}>
                  {i.code} {i.name}: {i.share_percent} %
                </li>
              ))}
              <li>{t("accounts.allocationTotal", { total: data.total_percent })}</li>
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function EditRow({ ledgerId, account, canUpdate }: { ledgerId: string; account: ManagedAccount; canUpdate: boolean }) {
  const t = useTranslations("Bookkeeping");
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(account.name);
  const [texts, setTexts] = useState((account.booking_texts ?? []).join("\n"));
  const [vat, setVat] = useState(account.vat_option);
  const [cash, setCash] = useState(account.relevant_for_cash_report);
  const [visible, setVisible] = useState(account.visible);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const patch = async (body: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    const res = await bff(`/api/bff/accounting/ledgers/${ledgerId}/accounts/${account.id}`, { method: "PATCH", body: JSON.stringify(body) });
    setBusy(false);
    if (res.ok) {
      setEditing(false);
      router.refresh();
    } else setError(res.message);
  };
  const save = (e: React.FormEvent) => {
    e.preventDefault();
    const bookingTexts = texts.split("\n").map((s) => s.trim()).filter(Boolean);
    if (bookingTexts.length > 3) {
      setError(t("accounts.tooManyTexts"));
      return;
    }
    void patch({ name, booking_texts: bookingTexts, vat_option: vat, relevant_for_cash_report: cash, visible });
  };
  return (
    <tr className={account.active ? undefined : "text-muted"}>
      <td className="tabular-nums">
        <Link href={`/buchhaltung/${ledgerId}/konten/${account.id}`} className="underline">
          {account.number}
        </Link>
      </td>
      <td>
        {editing ? (
          <form onSubmit={save} className="flex flex-col gap-2" aria-label={t("accounts.edit")}>
            <input aria-label={t("accounts.name")} required maxLength={200} className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("accounts.bookingTexts")}</span>
              <textarea className={ui.input} rows={3} value={texts} onChange={(e) => setTexts(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("accounts.vat")}</span>
              <select className={ui.input} value={vat} onChange={(e) => setVat(e.target.value)}>
                {VAT.map((v) => (
                  <option key={v} value={v}>
                    {t(`accounts.vatOptions.${v}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={cash} onChange={(e) => setCash(e.target.checked)} />
              {t("accounts.cashReport")}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={visible} onChange={(e) => setVisible(e.target.checked)} />
              {t("accounts.visible")}
            </label>
            <div className={ui.formActions}>
              <button type="submit" className={ui.primary} disabled={busy}>
                {t("accounts.save")}
              </button>
              <button type="button" className={ui.secondary} onClick={() => setEditing(false)}>
                {t("accounts.cancel")}
              </button>
            </div>
          </form>
        ) : (
          <>
            {account.name}
            {!account.visible ? <span className="ml-2 text-xs text-muted">{t("accounts.hidden")}</span> : null}
          </>
        )}
        {error ? (
          <p role="alert" className={ui.error}>
            {error}
          </p>
        ) : null}
      </td>
      <td>{t(`accounts.categories.${account.category}`)}</td>
      <td>
        <AllocationCell ledgerId={ledgerId} account={account} />
      </td>
      <td>{account.active ? t("accounts.active") : t("accounts.inactive")}</td>
      <td>
        {canUpdate && !editing ? (
          <span className="flex flex-wrap gap-1">
            <button type="button" className={ui.buttonSm} onClick={() => setEditing(true)}>
              {t("accounts.edit")}
            </button>
            <button
              type="button"
              className={ui.buttonSm}
              disabled={busy}
              onClick={() => {
                if (window.confirm(account.active ? t("accounts.confirmDeactivate") : t("accounts.confirmActivate"))) void patch({ active: !account.active });
              }}
            >
              {account.active ? t("accounts.deactivate") : t("accounts.activate")}
            </button>
          </span>
        ) : null}
      </td>
    </tr>
  );
}

/** Chart of accounts per ledger (M10-03): add, edit, deactivate; creditor sync (M10-05). */
export function AccountsManager({
  ledgerId,
  accounts,
  canCreate,
  canUpdate,
}: {
  ledgerId: string;
  accounts: ManagedAccount[];
  canCreate: boolean;
  canUpdate: boolean;
}) {
  const t = useTranslations("Bookkeeping");
  const router = useRouter();
  const [number, setNumber] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState<string>("cost");
  const [type, setType] = useState<string>("expense");
  const [vat, setVat] = useState<string>("none");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setInfo(null);
    const res = await bff(`/api/bff/accounting/ledgers/${ledgerId}/accounts`, {
      method: "POST",
      body: JSON.stringify({ number, name, category, type, vat_option: vat }),
    });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setNumber("");
    setName("");
    setInfo(t("accounts.created"));
    router.refresh();
  };
  const syncCreditors = async () => {
    setBusy(true);
    setError(null);
    const res = await bff<{ created: number; linked: number }>(`/api/bff/accounting/ledgers/${ledgerId}/sync-creditors`, { method: "POST" });
    setBusy(false);
    if (!res.ok) {
      setError(res.message);
      return;
    }
    setInfo(t("accounts.creditorsSynced", { created: res.data.created, linked: res.data.linked }));
    router.refresh();
  };

  return (
    <div className="flex flex-col gap-4">
      {canCreate ? (
        <form onSubmit={create} className={`${ui.card} flex flex-col gap-3`} aria-label={t("accounts.add")}>
          <h3 className="text-sm font-semibold">{t("accounts.add")}</h3>
          <div className="grid gap-3 sm:grid-cols-5">
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("accounts.number")}</span>
              <input required pattern="[0-9]{6}" className={ui.input} value={number} onChange={(e) => setNumber(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 sm:col-span-2">
              <span className={ui.label}>{t("accounts.name")}</span>
              <input required maxLength={200} className={ui.input} value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("accounts.category")}</span>
              <select className={ui.input} value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {t(`accounts.categories.${c}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("accounts.type")}</span>
              <select className={ui.input} value={type} onChange={(e) => setType(e.target.value)}>
                {TYPES.map((c) => (
                  <option key={c} value={c}>
                    {t(`accounts.types.${c}`)}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className={ui.label}>{t("accounts.vat")}</span>
              <select className={ui.input} value={vat} onChange={(e) => setVat(e.target.value)}>
                {VAT.map((v) => (
                  <option key={v} value={v}>
                    {t(`accounts.vatOptions.${v}`)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className={ui.formActions}>
            <button type="submit" className={ui.primary} disabled={busy}>
              {t("accounts.addSubmit")}
            </button>
            <button type="button" className={ui.secondary} disabled={busy} onClick={syncCreditors}>
              {t("accounts.syncCreditors")}
            </button>
          </div>
        </form>
      ) : null}
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      {info ? (
        <p role="status" className={ui.success}>
          {info}
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="mhvp-table">
          <thead>
            <tr>
              <th>{t("accounts.number")}</th>
              <th>{t("accounts.name")}</th>
              <th>{t("accounts.category")}</th>
              <th>{t("accounts.statementKind")}</th>
              <th>{t("accounts.state")}</th>
              <th>{t("accounts.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <EditRow key={a.id} ledgerId={ledgerId} account={a} canUpdate={canUpdate} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
