import { SITE } from "@/content/site";

/** Rendered by the root layout, so it is on every page (including 404s). */
export function TestModeBanner() {
  return (
    <aside aria-label="Test mode" className="banner">
      <p className="m-0 leading-[1.4]">
        <span aria-hidden="true">● </span>
        {SITE.testModeNotice}
      </p>
    </aside>
  );
}
