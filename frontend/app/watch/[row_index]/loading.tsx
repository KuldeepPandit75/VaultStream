export default function WatchLoading() {
  return (
    <div className="mx-auto max-w-[1400px] sm:px-6 sm:py-8 lg:px-8">
      <div className="shimmer aspect-video w-full bg-vault-900 sm:rounded-xl" />
      <div className="space-y-3 px-4 py-8 sm:px-0">
        <div className="shimmer h-8 w-2/3 max-w-md rounded bg-vault-850" />
        <div className="shimmer h-4 w-48 rounded bg-vault-850" />
        <div className="shimmer h-4 w-full max-w-3xl rounded bg-vault-850" />
      </div>
    </div>
  );
}
