import Link from "next/link";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`group flex items-center gap-2 ${className}`}
      aria-label="VaultStream home"
    >
      <span
        aria-hidden="true"
        className="grid size-8 place-items-center rounded-md bg-brand-500 font-mono text-lg font-bold text-vault-950 transition-transform duration-300 ease-out-quart group-hover:scale-105"
      >
        V
      </span>
      <span className="text-lg font-semibold tracking-tight">
        Vault<span className="text-brand-400">Stream</span>
      </span>
    </Link>
  );
}
