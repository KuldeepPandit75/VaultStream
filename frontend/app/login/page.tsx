import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth/AuthForm";
import { Logo } from "@/components/layout/Logo";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to VaultStream for personalised recommendations.",
};

export default async function LoginPage() {
  // Already signed in: no reason to show the form.
  if (await getCurrentUser()) redirect("/");

  return (
    <div className="mx-auto flex w-full max-w-md flex-col px-4 py-16 sm:py-24">
      <div className="mb-8 flex justify-center">
        <Logo />
      </div>
      <h1 className="text-center text-2xl font-semibold tracking-tight">
        Welcome back
      </h1>
      <p className="mt-2 text-center text-sm text-vault-muted">
        Sign in to pick up where you left off.
      </p>
      <div className="mt-8 rounded-2xl border border-vault-800 bg-vault-900/60 p-6 sm:p-8">
        {/* AuthForm reads useSearchParams for ?next=, so it needs a boundary. */}
        <Suspense fallback={<div className="shimmer h-72 rounded-lg bg-vault-850" />}>
          <AuthForm mode="login" />
        </Suspense>
      </div>
    </div>
  );
}
