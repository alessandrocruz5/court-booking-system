import type * as React from "react";
import type { ReactElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { COPIED_MS, CopyReference } from "../copy-reference";

/*
 * The web tests run in Node with no DOM, so this drives the component through a minimal hook
 * harness: `useState` keeps its slots between calls, and `useEffect` runs after each render with
 * the previous cleanup first. The component returns a plain <button>, so its markup renders
 * without calling any hooks again.
 */
const slots: unknown[] = [];
let cursor = 0;
let effects: React.EffectCallback[] = [];
let cleanups: (() => void)[] = [];

vi.mock("react", async (importActual) => {
  const actual = await importActual<typeof React>();
  return {
    ...actual,
    useState: (initial: unknown) => {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], (value: unknown) => (slots[index] = value)];
    },
    useEffect: (effect: React.EffectCallback) => {
      effects.push(effect);
    },
  };
});

const REFERENCE = "KC-7Q4M2X";

type ButtonProps = { onClick: () => Promise<void> };

/** Renders the component once, runs its effects, and returns the button. */
function render(): ReactElement<ButtonProps> {
  cursor = 0;
  effects = [];
  const element = CopyReference({ reference: REFERENCE }) as ReactElement<ButtonProps>;
  for (const cleanup of cleanups) cleanup();
  cleanups = [];
  for (const effect of effects) {
    const cleanup = effect();
    if (typeof cleanup === "function") cleanups.push(cleanup);
  }
  return element;
}

const writeText = vi.fn(async (_text: string) => {});

beforeEach(() => {
  slots.length = 0;
  cleanups = [];
  vi.useFakeTimers();
  vi.stubGlobal("navigator", { clipboard: { writeText } });
});

afterEach(() => {
  writeText.mockReset();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("CopyReference", () => {
  it("writes the reference to the clipboard and reads Copied, then Copy after 2 s", async () => {
    const button = render();
    expect(renderToStaticMarkup(button)).toContain(">Copy</span>");
    expect(renderToStaticMarkup(button)).toContain('aria-live="polite"');

    await button.props.onClick();
    expect(writeText).toHaveBeenCalledWith(REFERENCE);
    expect(renderToStaticMarkup(render())).toContain(">Copied</span>");

    vi.advanceTimersByTime(COPIED_MS);
    expect(renderToStaticMarkup(render())).toContain(">Copy</span>");
  });

  it("keeps the Copy label when the clipboard refuses", async () => {
    writeText.mockRejectedValueOnce(new Error("denied"));

    await render().props.onClick();
    expect(renderToStaticMarkup(render())).toContain(">Copy</span>");
  });
});
