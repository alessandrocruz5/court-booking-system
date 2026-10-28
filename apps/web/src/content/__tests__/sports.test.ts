import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { SPORT_BG, SPORT_COLORS } from "../sports";

// The drift guard: the sport colours against the backend's catalog, docs/api/fixtures/catalog.json.
const CATALOG = fileURLToPath(
  new URL("../../../../../docs/api/fixtures/catalog.json", import.meta.url),
);

const catalog = JSON.parse(readFileSync(CATALOG, "utf8")) as {
  sports: { id: string }[];
};

describe("sport colours against the backend catalog fixture", () => {
  it("has a colour for every sport and no others", () => {
    expect(Object.keys(SPORT_COLORS).sort()).toEqual(catalog.sports.map((s) => s.id).sort());
  });

  it("uses a hex colour for each sport", () => {
    for (const color of Object.values(SPORT_COLORS)) {
      expect(color).toMatch(/^#[0-9a-f]{6}$/);
    }
  });

  it("matches the --color-sport-* tokens behind the SPORT_BG classes", () => {
    const css = readFileSync(
      fileURLToPath(new URL("../../../app/globals.css", import.meta.url)),
      "utf8",
    );
    for (const [id, color] of Object.entries(SPORT_COLORS)) {
      expect(css).toContain(`--color-sport-${id}: ${color};`);
      expect(SPORT_BG[id as keyof typeof SPORT_BG]).toBe(`bg-sport-${id}`);
    }
  });
});
