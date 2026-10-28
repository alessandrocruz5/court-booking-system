// Paints at once while the page awaits the catalog, so a cold backend never blanks the screen.
export default function BookLoading() {
  return (
    <main className="wrap" aria-busy="true" aria-label="Loading">
      <div className="h-3.5 w-24 animate-pulse rounded bg-line-soft" />
      <div className="mt-3 mb-7 h-11 w-64 max-w-full animate-pulse rounded bg-line-soft" />
      <div className="grid grid-cols-1 items-start gap-7 min-[900px]:grid-cols-[minmax(0,1fr)_340px]">
        <div className="grid min-w-0 gap-3.5">
          {[
            { id: "sport", tiles: 5, tile: "h-[88px]" },
            { id: "day", tiles: 7, tile: "h-11" },
            { id: "time", tiles: 8, tile: "h-[76px]" },
            { id: "details", tiles: 3, tile: "h-11" },
          ].map((card) => (
            <div key={card.id} className="rounded-2xl border border-line-soft bg-white p-[22px]">
              <div className="flex items-center gap-2.5">
                <div className="size-[26px] animate-pulse rounded-full bg-line-soft" />
                <div className="h-5 w-32 animate-pulse rounded bg-line-soft" />
              </div>
              <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(90px,1fr))] gap-2">
                {Array.from({ length: card.tiles }, (_, i) => (
                  <div key={i} className={`${card.tile} animate-pulse rounded-[10px] bg-hair`} />
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="hidden h-[380px] animate-pulse rounded-2xl bg-line-soft min-[900px]:block" />
      </div>
    </main>
  );
}
