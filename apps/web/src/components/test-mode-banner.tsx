import { SITE } from "@/content/site";

/** Rendered by the root layout, so it is on every page (including 404s). */
export function TestModeBanner() {
  return (
    <aside aria-label="Test mode" className="banner">
      <span aria-hidden="true" className="inline-block size-[7px] rounded-full bg-[#4ade80]" />
      <p className="m-0 leading-[1.4]">{SITE.testModeNotice}</p>
    </aside>
  );
}
