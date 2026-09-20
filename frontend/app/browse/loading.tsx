import { MovieGridSkeleton } from "@/components/catalog/MovieGrid";

export default function BrowseLoading() {
  return (
    <div className="mx-auto max-w-[1600px] px-4 py-8 sm:px-6 lg:px-8">
      <div className="shimmer h-8 w-48 rounded bg-vault-850" />
      <div className="mt-8 lg:grid lg:grid-cols-[220px_1fr] lg:gap-10">
        <div className="hidden space-y-4 lg:block">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="shimmer h-24 rounded-lg bg-vault-850" />
          ))}
        </div>
        <MovieGridSkeleton />
      </div>
    </div>
  );
}
