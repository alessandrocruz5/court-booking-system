/** The sport tag colours, one per sport id in `docs/api/fixtures/catalog.json` (tested against it). */
export const SPORT_COLORS = {
  basketball: "#e0662d",
  volleyball: "#d4a017",
  tennis: "#5b9a1e",
  badminton: "#2b7fc4",
  pickleball: "#14958a",
} as const;

/**
 * The tag colour as a background class, from the `--color-sport-*` tokens in `app/globals.css`.
 * Written out in full so Tailwind generates each one; never an inline style.
 */
export const SPORT_BG = {
  basketball: "bg-sport-basketball",
  volleyball: "bg-sport-volleyball",
  tennis: "bg-sport-tennis",
  badminton: "bg-sport-badminton",
  pickleball: "bg-sport-pickleball",
} as const satisfies Record<keyof typeof SPORT_COLORS, string>;
