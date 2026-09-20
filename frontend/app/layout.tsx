import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";

import { SessionProvider } from "@/components/auth/SessionProvider";
import { SiteFooter } from "@/components/layout/SiteFooter";
import { SiteHeader } from "@/components/layout/SiteHeader";
import { getCurrentUser } from "@/lib/session";
import "./globals.css";

// Self-hosted via the `geist` package rather than next/font/google: the font
// files ship with the dependency, so builds never depend on reaching
// fonts.googleapis.com (which fails in this environment and in offline CI).

export const metadata: Metadata = {
  title: {
    default: "VaultStream",
    template: "%s · VaultStream",
  },
  description:
    "Browse a catalogue of over 44,000 films with trailers and personalised recommendations.",
  applicationName: "VaultStream",
};

export default async function RootLayout({ children }: LayoutProps<"/">) {
  // Resolved server-side from the httpOnly cookie, then handed to Client
  // Components through context. The token itself never reaches the browser.
  const user = await getCurrentUser();

  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable} h-full antialiased`}
    >
      <body className="flex min-h-full flex-col bg-vault-950">
        {/* First tab stop: lets keyboard users bypass the header and nav. */}
        <a
          href="#main"
          className="sr-only-focusable absolute left-4 top-4 z-[100] rounded-md bg-brand-500 px-4 py-2 text-sm font-semibold text-vault-950"
        >
          Skip to content
        </a>
        <SessionProvider user={user}>
          <SiteHeader />
          <main id="main" className="flex-1">
            {children}
          </main>
          <SiteFooter />
        </SessionProvider>
      </body>
    </html>
  );
}
