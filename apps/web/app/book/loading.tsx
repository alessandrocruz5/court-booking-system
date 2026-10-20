// Paints at once while the page awaits the catalog, so a cold backend never blanks the screen.
export default function BookLoading() {
  return (
    <main className="wrap" aria-busy="true" aria-label="Loading">
      <div className="h-4 w-24 animate-pulse rounded bg-line" />
      <div className="mt-3 h-10 w-64 max-w-full animate-pulse rounded bg-line" />
      <div className="mt-4 h-5 w-56 max-w-full animate-pulse rounded bg-line" />
      <div className="mt-8 grid gap-8">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 animate-pulse rounded-xl bg-line" />
          ))}
        </div>
        <div className="flex gap-2">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-11 w-20 animate-pulse rounded-lg bg-line" />
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {[0, 1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-11 w-20 animate-pulse rounded-lg bg-line" />
          ))}
        </div>
      </div>
    </main>
  );
}
