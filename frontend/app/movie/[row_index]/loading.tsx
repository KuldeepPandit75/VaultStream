export default function MovieDetailLoading() {
  return (
    <div className="mx-auto max-w-[1600px] px-4 py-10 sm:px-6 lg:px-8 lg:pt-16">
      <div className="flex flex-col gap-8 md:flex-row md:gap-10">
        <div className="w-40 shrink-0 sm:w-48 lg:w-60">
          <div className="shimmer aspect-[2/3] rounded-card bg-vault-850" />
        </div>
        <div className="flex-1 space-y-4">
          <div className="shimmer h-10 w-3/4 max-w-xl rounded bg-vault-850" />
          <div className="shimmer h-4 w-56 rounded bg-vault-850" />
          <div className="flex gap-2">
            {Array.from({ length: 3 }, (_, index) => (
              <div key={index} className="shimmer h-7 w-24 rounded-full bg-vault-850" />
            ))}
          </div>
          <div className="space-y-2 pt-3">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="shimmer h-4 w-full max-w-3xl rounded bg-vault-850" />
            ))}
          </div>
          <div className="shimmer mt-6 h-12 w-44 rounded-full bg-vault-850" />
        </div>
      </div>
    </div>
  );
}
