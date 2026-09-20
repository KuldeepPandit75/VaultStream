import Link from "next/link";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center px-4 py-24 text-center">
      <p className="font-mono text-5xl font-bold text-brand-500">404</p>
      <h1 className="mt-4 text-2xl font-semibold">Page not found</h1>
      <p className="mt-3 text-sm leading-relaxed text-vault-muted">
        The page you are looking for does not exist or has moved.
      </p>
      <Link
        href="/browse"
        className="mt-8 rounded-full bg-brand-500 px-6 py-2.5 text-sm font-semibold text-vault-950 transition-colors hover:bg-brand-400"
      >
        Browse the catalogue
      </Link>
    </div>
  );
}
