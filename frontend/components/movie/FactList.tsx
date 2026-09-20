import { formatCurrency, formatLanguage } from "@/lib/format";
import type { MovieDetail } from "@/lib/types";

/** Secondary facts. Rows with no data are omitted rather than shown as "—". */
export function FactList({ movie }: { movie: MovieDetail }) {
  const facts: Array<{ label: string; value: string }> = [];

  if (movie.status) facts.push({ label: "Status", value: movie.status });

  const language = formatLanguage(movie.original_language);
  if (language) facts.push({ label: "Original language", value: language });

  if (movie.original_title && movie.original_title !== movie.title) {
    facts.push({ label: "Original title", value: movie.original_title });
  }

  const budget = formatCurrency(movie.budget);
  if (budget) facts.push({ label: "Budget", value: budget });

  const revenue = formatCurrency(movie.revenue);
  if (revenue) facts.push({ label: "Revenue", value: revenue });

  if (movie.release_date) {
    facts.push({
      label: "Release date",
      value: new Date(movie.release_date).toLocaleDateString("en-GB", {
        day: "numeric",
        month: "long",
        year: "numeric",
      }),
    });
  }

  if (movie.omdb) {
    if (movie.omdb.country) facts.push({ label: "Country", value: movie.omdb.country });
    if (movie.omdb.box_office && movie.omdb.box_office !== "N/A") {
      facts.push({ label: "Box Office", value: movie.omdb.box_office });
    }
    if (movie.omdb.production && movie.omdb.production !== "N/A") {
      facts.push({ label: "Production", value: movie.omdb.production });
    }
    if (movie.omdb.dvd && movie.omdb.dvd !== "N/A") {
      facts.push({ label: "DVD Release", value: movie.omdb.dvd });
    }
  }

  if (facts.length === 0) return null;

  return (
    <section aria-labelledby="facts-heading">
      <h2 id="facts-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-vault-muted">
        Details
      </h2>
      <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
        {facts.map((fact) => (
          <div key={fact.label}>
            <dt className="text-xs uppercase tracking-wide text-vault-faint">
              {fact.label}
            </dt>
            <dd className="mt-0.5 text-sm text-vault-text">{fact.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
