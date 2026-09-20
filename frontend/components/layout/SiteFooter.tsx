export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-vault-850 bg-vault-950">
      <div className="mx-auto max-w-[1600px] px-4 py-10 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="max-w-md space-y-2">
            <p className="text-sm font-semibold text-vault-text">VaultStream</p>
            <p className="text-sm leading-relaxed text-vault-muted">
              A demonstration streaming catalogue. Playback is limited to
              official trailers.
            </p>
          </div>
          <div className="text-sm text-vault-faint">
            <p>
              Metadata and artwork courtesy of{" "}
              <a
                href="https://www.themoviedb.org/"
                target="_blank"
                rel="noreferrer noopener"
                className="text-vault-muted underline decoration-vault-600 underline-offset-4 transition-colors hover:text-brand-400"
              >
                TMDB
              </a>
              .
            </p>
            <p className="mt-1">
              This product uses the TMDB API but is not endorsed or certified by
              TMDB.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
