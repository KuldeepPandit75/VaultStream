import type { Metadata } from "next";

import { SignOutEverywhere } from "@/components/auth/SignOutEverywhere";
import { requireUser } from "@/lib/session";

export const metadata: Metadata = {
  title: "Account",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-GB", {
    dateStyle: "long",
    timeStyle: "short",
  });
}

export default async function AccountPage() {
  // Protected route: anonymous visitors are redirected to /login?next=/account.
  const user = await requireUser("/account");

  return (
    <div className="mx-auto max-w-2xl px-4 py-12 sm:px-6">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Account</h1>

      <dl className="mt-8 divide-y divide-vault-850 rounded-xl border border-vault-800">
        <div className="flex flex-wrap justify-between gap-2 px-5 py-4">
          <dt className="text-sm text-vault-faint">Display name</dt>
          <dd className="text-sm text-vault-text">{user.display_name}</dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2 px-5 py-4">
          <dt className="text-sm text-vault-faint">Email</dt>
          <dd className="text-sm text-vault-text">{user.email}</dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2 px-5 py-4">
          <dt className="text-sm text-vault-faint">Member since</dt>
          <dd className="text-sm text-vault-text">{formatDate(user.created_at)}</dd>
        </div>
        <div className="flex flex-wrap justify-between gap-2 px-5 py-4">
          <dt className="text-sm text-vault-faint">Last sign-in</dt>
          <dd className="text-sm text-vault-text">{formatDate(user.last_login_at)}</dd>
        </div>
      </dl>

      <section className="mt-10 rounded-xl border border-vault-800 p-5">
        <h2 className="text-sm font-semibold text-vault-text">Sessions</h2>
        <p className="mt-1.5 text-sm leading-relaxed text-vault-muted">
          Signing out everywhere revokes every device that is currently signed in
          to this account.
        </p>
        <div className="mt-4">
          <SignOutEverywhere />
        </div>
      </section>
    </div>
  );
}
