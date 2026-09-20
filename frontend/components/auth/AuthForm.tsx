"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { AuthError, login, register } from "@/lib/auth-client";

type Mode = "login" | "register";

/** Only allow same-site relative redirects, never an absolute URL. */
function safeNext(raw: string | null): string {
  if (!raw) return "/";
  if (!raw.startsWith("/") || raw.startsWith("//")) return "/";
  return raw;
}

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const formId = useId();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const isRegister = mode === "register";
  const next = safeNext(searchParams.get("next"));

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    setFieldErrors({});

    try {
      if (isRegister) {
        await register(email, password, displayName);
      } else {
        await login(email, password);
      }
      // router.refresh() re-runs the root layout so the header picks up the new
      // session; replace() keeps the auth page out of the back-button history.
      router.replace(next);
      router.refresh();
    } catch (cause) {
      if (cause instanceof AuthError) {
        setError(cause.failure.message);
        setFieldErrors(cause.failure.fieldErrors ?? {});
      } else {
        setError("Something went wrong. Please try again.");
      }
      setIsSubmitting(false);
    }
  }

  const inputClass =
    "w-full rounded-lg border bg-vault-850 px-3.5 py-2.5 text-sm text-vault-text placeholder:text-vault-faint transition-colors focus:outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-400";

  const borderFor = (field: string) =>
    fieldErrors[field] ? "border-negative" : "border-vault-700 hover:border-vault-600";

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-5">
      {/* Assertive so a submit failure is announced immediately. */}
      <div aria-live="assertive">
        {error && (
          <p
            role="alert"
            className="rounded-lg border border-negative/40 bg-negative/10 px-3.5 py-2.5 text-sm text-negative"
          >
            {error}
          </p>
        )}
      </div>

      {isRegister && (
        <div>
          <label
            htmlFor={`${formId}-name`}
            className="mb-1.5 block text-sm font-medium text-vault-muted"
          >
            Display name
          </label>
          <input
            id={`${formId}-name`}
            name="display_name"
            type="text"
            autoComplete="name"
            required
            maxLength={80}
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            aria-invalid={Boolean(fieldErrors.display_name)}
            aria-describedby={
              fieldErrors.display_name ? `${formId}-name-error` : undefined
            }
            className={`${inputClass} ${borderFor("display_name")}`}
          />
          {fieldErrors.display_name && (
            <p id={`${formId}-name-error`} className="mt-1.5 text-xs text-negative">
              {fieldErrors.display_name}
            </p>
          )}
        </div>
      )}

      <div>
        <label
          htmlFor={`${formId}-email`}
          className="mb-1.5 block text-sm font-medium text-vault-muted"
        >
          Email
        </label>
        <input
          id={`${formId}-email`}
          name="email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          aria-invalid={Boolean(fieldErrors.email)}
          aria-describedby={fieldErrors.email ? `${formId}-email-error` : undefined}
          className={`${inputClass} ${borderFor("email")}`}
        />
        {fieldErrors.email && (
          <p id={`${formId}-email-error`} className="mt-1.5 text-xs text-negative">
            {fieldErrors.email}
          </p>
        )}
      </div>

      <div>
        <label
          htmlFor={`${formId}-password`}
          className="mb-1.5 block text-sm font-medium text-vault-muted"
        >
          Password
        </label>
        <input
          id={`${formId}-password`}
          name="password"
          type="password"
          autoComplete={isRegister ? "new-password" : "current-password"}
          required
          minLength={isRegister ? 8 : undefined}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          aria-invalid={Boolean(fieldErrors.password)}
          aria-describedby={
            fieldErrors.password
              ? `${formId}-password-error`
              : isRegister
                ? `${formId}-password-hint`
                : undefined
          }
          className={`${inputClass} ${borderFor("password")}`}
        />
        {isRegister && !fieldErrors.password && (
          <p id={`${formId}-password-hint`} className="mt-1.5 text-xs text-vault-faint">
            At least 8 characters.
          </p>
        )}
        {fieldErrors.password && (
          <p id={`${formId}-password-error`} className="mt-1.5 text-xs text-negative">
            {fieldErrors.password}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isSubmitting}
        className="w-full rounded-full bg-brand-500 px-6 py-3 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400 disabled:cursor-wait disabled:opacity-70"
      >
        {isSubmitting
          ? isRegister
            ? "Creating account…"
            : "Signing in…"
          : isRegister
            ? "Create account"
            : "Sign in"}
      </button>

      <p className="text-center text-sm text-vault-muted">
        {isRegister ? "Already have an account? " : "New to VaultStream? "}
        <Link
          href={
            isRegister
              ? `/login${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`
              : `/register${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`
          }
          className="font-medium text-brand-400 transition-colors hover:text-brand-300"
        >
          {isRegister ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </form>
  );
}
