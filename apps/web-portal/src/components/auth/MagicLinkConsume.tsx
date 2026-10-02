"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { bff } from "@/lib/bff";
import { adoptAccountLocale } from "@/lib/locale-sync";
import { ui } from "@/lib/ui";

type ConsumeResult =
  | { status: "ok" }
  | { status: "code_required"; link_id: string; tenant_id: string }
  // M2-04: the tenant policy requires TOTP (or its setup); the BFF keeps the step token.
  | { status: "mfa_required" | "mfa_setup_required" };

/** M2-04: next login step after the link or the e-mail code, null when the session is issued. */
function stepPath(status: string): string | null {
  if (status === "mfa_required") return "/anmelden/zweiter-faktor";
  if (status === "mfa_setup_required") return "/anmelden/zweiter-faktor-einrichten";
  return null;
}

type State =
  | { step: "consuming" }
  | { step: "code"; linkId: string; tenantId: string }
  | { step: "done" }
  | { step: "error"; message: string };

/** M21-01: redeems the link once on mount; "code_required" asks for the mailed e-mail code
 *  (optional second factor, switched on per account by the management). The link itself is
 *  never shown again, only the outcome. */
export function MagicLinkConsume({ token }: { token?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [state, setState] = useState<State>({ step: "consuming" });
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const consumed = useRef(false);

  useEffect(() => {
    if (!token) {
      setState({ step: "error", message: t("magicLink.invalid") });
      return;
    }
    if (consumed.current) return;
    consumed.current = true;
    void (async () => {
      const result = await bff<ConsumeResult>("/api/session/magic-link/consume", {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      if (!result.ok) {
        setState({ step: "error", message: t("magicLink.invalid") });
        return;
      }
      if (result.data.status === "ok") {
        setState({ step: "done" });
        await adoptAccountLocale();
        router.push("/start");
        router.refresh();
        return;
      }
      const consumedStep = stepPath(result.data.status);
      if (consumedStep) {
        setState({ step: "done" });
        router.push(consumedStep);
        return;
      }
      if (result.data.status !== "code_required") return;
      setState({ step: "code", linkId: result.data.link_id, tenantId: result.data.tenant_id });
    })();
    // token is read once on mount; the link must not be redeemed a second time on a rerender.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function verifyCode(event: React.FormEvent) {
    event.preventDefault();
    if (state.step !== "code") return;
    setBusy(true);
    const result = await bff<{ status: string }>("/api/session/magic-link/verify-code", {
      method: "POST",
      body: JSON.stringify({ tenant_id: state.tenantId, link_id: state.linkId, code: code.trim() }),
    });
    setBusy(false);
    if (!result.ok) {
      setState({ step: "error", message: t("magicLink.invalid") });
      return;
    }
    setState({ step: "done" });
    const codeStep = stepPath(result.data.status);
    if (codeStep) {
      router.push(codeStep);
      return;
    }
    await adoptAccountLocale();
    router.push("/start");
    router.refresh();
  }

  if (state.step === "consuming" || state.step === "done") {
    return <p className="text-sm text-muted">{t("magicLink.checking")}</p>;
  }
  if (state.step === "error") {
    return (
      <div className="flex flex-col gap-3">
        <p role="alert" className={ui.alert}>
          {state.message}
        </p>
        <button type="button" className={ui.primary} onClick={() => router.push("/anmelden")}>
          {t("magicLink.backToPassword")}
        </button>
      </div>
    );
  }
  return (
    <form onSubmit={verifyCode} noValidate className="flex flex-col gap-3" aria-label={t("magicLink.codeTitle")}>
      <p className="text-sm text-muted">{t("magicLink.codeHint")}</p>
      <div>
        <label htmlFor="magic-link-code" className={ui.label}>
          {t("code")}
        </label>
        <input
          id="magic-link-code"
          className={ui.input}
          autoComplete="one-time-code"
          // eslint-disable-next-line jsx-a11y/no-autofocus -- sign-in step: the single input is the intended focus target
          autoFocus
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
      </div>
      <button type="submit" className={ui.primary} disabled={busy}>
        {busy ? t("submitting") : t("verify")}
      </button>
    </form>
  );
}
