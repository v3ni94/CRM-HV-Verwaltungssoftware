"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { bff } from "@/lib/bff";
import { ui } from "@/lib/ui";

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
    const result = await bff<{ status: string }>("/api/session/login", {
      method: "POST",
      body: JSON.stringify(values),
    });
    if (!result.ok) {
      setError(result.message);
      return;
    }
    const params = new URLSearchParams();
    if (result.data.status === "mfa_setup_required") params.set("einrichten", "1");
    if (next) params.set("next", next);
    const query = params.toString();
    router.push(`/anmelden/zweiter-faktor${query ? `?${query}` : ""}`);
  });

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
    </form>
  );
}
