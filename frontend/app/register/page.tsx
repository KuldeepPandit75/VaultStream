import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { AuthForm } from "@/components/auth/AuthForm";
import { Logo } from "@/components/layout/Logo";
import { getCurrentUser } from "@/lib/session";

export const metadata: Metadata = {
  title: "Create an account",
  description:
    "Create a VaultStream account to track what you watch and get recommendations.",
};

export default async function RegisterPage() {
  if (await getCurrentUser()) redirect("/");

  return (
    <div className="mx-auto flex w-full max-w-md flex-col px-4 py-16 sm:py-24">
      <div className="mb-8 flex justify-center">
        <Logo />
      </div>
      <h1 className="text-center text-2xl font-semibold tracking-tight">
        Create your account
      </h1>
      <p className="mt-2 text-center text-sm text-vault-muted">
        Track what you watch and get recommendations based on it.
      </p>
      <div className="mt-8 rounded-2xl border border-vault-800 bg-vault-900/60 p-6 sm:p-8">
        <Suspense fallback={<div className="shimmer h-96 rounded-lg bg-vault-850" />}>
          <AuthForm mode="register" />
        </Suspense>
      </div>
    </div>
  );
}
