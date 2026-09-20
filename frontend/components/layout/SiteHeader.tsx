"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { UserMenu } from "@/components/auth/UserMenu";
import { SearchBox } from "@/components/catalog/SearchBox";
import { Logo } from "@/components/layout/Logo";

const NAV_LINKS = [
  { href: "/", label: "Home" },
  { href: "/browse", label: "Browse" },
] as const;

export function SiteHeader() {
  const pathname = usePathname();
  const [isScrolled, setIsScrolled] = useState(false);

  // Transparent over hero artwork at the top, solid once scrolled - the
  // standard OTT header treatment.
  useEffect(() => {
    const onScroll = () => setIsScrolled(window.scrollY > 16);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 border-b transition-colors duration-300 ${
        isScrolled
          ? "border-vault-800 bg-vault-950/85 backdrop-blur-md"
          : "border-transparent bg-gradient-to-b from-vault-950/90 to-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-4 px-4 sm:gap-6 sm:px-6 lg:px-8">
        <Logo />

        <nav aria-label="Main" className="hidden sm:block">
          <ul className="flex items-center gap-1">
            {NAV_LINKS.map((link) => {
              const isActive =
                link.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(link.href);
              return (
                <li key={link.href}>
                  <Link
                    href={link.href}
                    aria-current={isActive ? "page" : undefined}
                    className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                      isActive
                        ? "text-vault-text"
                        : "text-vault-muted hover:text-vault-text"
                    }`}
                  >
                    {link.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="ml-auto w-full max-w-[14rem] sm:max-w-xs">
          {/* SearchBox reads useSearchParams, which requires a Suspense boundary. */}
          <Suspense fallback={<div className="h-9 rounded-full bg-vault-850" />}>
            <SearchBox />
          </Suspense>
        </div>

        <UserMenu />
      </div>
    </header>
  );
}
