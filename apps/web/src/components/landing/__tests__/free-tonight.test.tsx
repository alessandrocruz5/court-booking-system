import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getAvailabilityOnce, getCatalog } from "@/lib/api/client";
import type * as Client from "@/lib/api/client";
import type { Availability, Catalog, Sport } from "@/lib/api/schemas";
import { FreeTonight } from "../free-tonight";

vi.mock("@/lib/api/client", async (importActual) => {
  // The real ApiError; only the network calls are faked.
  const actual = await importActual<typeof Client>();
  return { ...actual, getCatalog: vi.fn(), getAvailabilityOnce: vi.fn() };
});

// connection() throws outside a request; the page awaits it so the build never calls the API.
vi.mock("next/server", () => ({ connection: vi.fn(async () => {}) }));

// Read at run time, not imported: docs/ isn't in the web image's build context.
const catalog = JSON.parse(
  readFileSync(
    new URL("../../../../../../docs/api/fixtures/catalog.json", import.meta.url),
    "utf8",
  ),
) as Catalog;

const catalogMock = vi.mocked(getCatalog);
const availabilityMock = vi.mocked(getAvailabilityOnce);

/** Wed 28 Oct 2026, Asia/Manila; the next day is Thu 29 Oct. */
const WEEKDAY = new Date("2026-10-28T12:00:00+08:00");
/** Sun 25 Oct 2026, Asia/Manila. */
const WEEKEND = new Date("2026-10-25T12:00:00+08:00");

/** An availability answer whose courts start at the given hours, one list per court. */
function availability(sport: Sport, courtStarts: number[][]): Availability {
  return {
    date: "2026-10-28",
    sport,
    coverage: "full",
    hours: 1,
    courts: courtStarts.map((hours, i) => ({
      code: `c-${i + 1}`,
      name: `Court ${i + 1}`,
      starts: hours.map((hour) => ({ hour, price_centavos: 50000, peak: hour >= 17 })),
    })),
  };
}

/** Answers per sport; any sport not listed has no free start left tonight. */
function mockAvailability(bySport: Partial<Record<Sport, number[][]>>) {
  availabilityMock.mockImplementation(async (_date, sport) =>
    availability(sport, bySport[sport] ?? [[]]),
  );
}

async function render(): Promise<string> {
  return renderToStaticMarkup(await FreeTonight({ loadCatalog: getCatalog }));
}

const consoleSpies: ReturnType<typeof vi.spyOn>[] = [];

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(WEEKDAY);
  catalogMock.mockResolvedValue(catalog);
  for (const method of ["log", "info", "warn", "error", "debug"] as const) {
    consoleSpies.push(vi.spyOn(console, method).mockImplementation(() => {}));
  }
});

afterEach(() => {
  vi.useRealTimers();
  catalogMock.mockReset();
  availabilityMock.mockReset();
  consoleSpies.length = 0;
  vi.restoreAllMocks();
});

describe("FreeTonight", () => {
  it("shows a sport's earliest free hour across its courts, linking to that start", async () => {
    mockAvailability({
      tennis: [
        [20, 21],
        [18, 22],
      ],
    });

    const html = await render();
    expect(html).toContain("Free tonight");
    expect(html).toContain("Wed 28 Oct");
    expect(html).toContain("Tennis");
    expect(html).toContain("Next free 6 PM");
    expect(html).toContain('href="/book?sport=tennis&amp;date=2026-10-28&amp;start=18"');
    expect(availabilityMock).toHaveBeenCalledWith("2026-10-28", "tennis", "full", 1);
  });

  it("asks for every catalog sport, as one-hour full-court starts", async () => {
    mockAvailability({});

    await render();
    expect(availabilityMock).toHaveBeenCalledTimes(catalog.sports.length);
    for (const sport of catalog.sports) {
      expect(availabilityMock).toHaveBeenCalledWith("2026-10-28", sport.id, "full", 1);
    }
  });

  it("shows Full tonight for a sport with no starts, linking to tomorrow", async () => {
    mockAvailability({ tennis: [[20]] });

    const html = await render();
    expect(html).toContain("Full tonight");
    expect(html).toContain('href="/book?sport=basketball&amp;date=2026-10-29"');
    expect(html).not.toContain("start=18");
  });

  it("marks peak rates only when the first free hour is peak", async () => {
    mockAvailability({ tennis: [[9]], badminton: [[20]] });
    expect(await render()).not.toContain("peak rates");

    mockAvailability({ tennis: [[17]] });
    expect(await render()).toContain("Wed 28 Oct · peak rates");
  });

  it("marks peak rates all day on a weekend", async () => {
    vi.setSystemTime(WEEKEND);
    mockAvailability({ tennis: [[9]] });

    expect(await render()).toContain("Sun 25 Oct · peak rates");
  });

  it("does not claim peak rates when every sport is full", async () => {
    vi.setSystemTime(WEEKEND);
    mockAvailability({});

    expect(await render()).not.toContain("peak rates");
  });

  it("leaves out a sport whose call fails and keeps the rest", async () => {
    availabilityMock.mockImplementation(async (_date, sport) => {
      if (sport === "basketball") throw new ApiError(0, "unavailable");
      return availability(sport, [[8]]);
    });

    const html = await render();
    expect(html).not.toContain("Basketball");
    expect(html).toContain("Tennis");
    expect(html).toContain("Next free 8 AM");
  });

  it("renders nothing when every call rejects", async () => {
    availabilityMock.mockRejectedValue(new ApiError(0, "unavailable"));

    expect(await render()).toBe("");
  });

  it("renders nothing when the catalog can't be loaded", async () => {
    catalogMock.mockRejectedValue(new ApiError(0, "unavailable"));

    expect(await render()).toBe("");
    expect(availabilityMock).not.toHaveBeenCalled();
  });
});
