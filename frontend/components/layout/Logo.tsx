import Link from "next/link";
import Image from "next/image";

export function Logo({ className = "" }: { className?: string }) {
  return (
    <Link
      href="/"
      className={`group flex items-center gap-2 ${className}`}
      aria-label="VaultStream home"
    >
      <Image
        src="/logo.png"
        alt="VaultStream Logo"
        width={32}
        height={32}
        className="size-8 rounded-md transition-transform duration-300 ease-out-quart group-hover:scale-105"
      />
      <span className="text-lg font-semibold tracking-tight">
        Vault<span className="text-brand-400">Stream</span>
      </span>
    </Link>
  );
}
