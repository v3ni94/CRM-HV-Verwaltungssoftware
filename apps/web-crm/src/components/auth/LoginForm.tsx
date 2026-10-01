"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { bff } from "@/lib/bff";
import { safeNext, withNext } from "@/lib/next-path";
import { ui } from "@/lib/ui";
import { signInWithPasskey } from "@/lib/webauthn";

type Values = { email: string; password: string };

export function LoginForm({ next }: { next?: string }) {
  const t = useTranslations("Auth");
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const schema = z.object({
    email: z.email(t("emailInvalid")),
    password: z.string().min(1, t("passwordRequired")).max(256),
  });
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: "", password: "" } });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    const result = await bff<{ status: string; tenant_id?: string | null }>("/api/session/login", {
      method: "POST",
      body: JSON.stringify(values),
    });
    if (!result.ok) {
      setError(result.message);
      return;
    }
    if (result.data.status === "ok") {
      // Password alone was enough (no second factor enabled, or a trusted device).
      // Without a selected tenant the tenant selection comes first and keeps the target.
      router.push(result.data.tenant_id ? safeNext(next) : withNext("/mandant", next));
      router.refresh();
      return;
    }
    router.push(withNext("/anmelden/zweiter-faktor", next));
  });

  // S16-01: passwordless sign in, only with a passkey registered "ohne Passwort".
  async function onPasskey() {
    setError(null);
    const result = await signInWithPasskey("passwordless");
    if (!result.ok) {
      setError(result.reason === "unsupported" ? t("passkeyUnsupported") : result.reason === "aborted" ? t("passkeyAborted") : (result.message ?? null));
      return;
    }
    router.push(result.tenant_id ? safeNext(next) : withNext("/mandant", next));
    router.refresh();
  }

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3" aria-label={t("loginTitle")}>
      {error ? (
        <p role="alert" className={ui.alert}>
          {error}
        </p>
      ) : null}
      <div>
        <label htmlFor="email" className={ui.label}>
          {t("email")}
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          className={ui.input}
          aria-invalid={!!errors.email}
          {...register("email")}
        />
        {errors.email ? <p className={ui.error}>{errors.email.message}</p> : null}
      </div>
      <div>
        <label htmlFor="password" className={ui.label}>
          {t("password")}
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          className={ui.input}
          aria-invalid={!!errors.password}
          {...register("password")}
        />
        {errors.password ? <p className={ui.error}>{errors.password.message}</p> : null}
      </div>
      <button type="submit" className={ui.primary} disabled={isSubmitting}>
        {isSubmitting ? t("submitting") : t("submit")}
      </button>
      <button type="button" className={ui.button} disabled={isSubmitting} onClick={() => void onPasskey()}>
        {t("passkeyLogin")}
      </button>
    </form>
  );
}
