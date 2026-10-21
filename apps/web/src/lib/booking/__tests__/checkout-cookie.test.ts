import { describe, expect, it } from "vitest";
import {
  CHECKOUT_COOKIE,
  MAX_CHECKOUTS,
  addCheckout,
  isReference,
  parseCheckouts,
  pickCheckout,
} from "../checkout-cookie";

const A = "KC-AAAAAA";
const B = "KC-BBBBBB";
const C = "KC-CCCCCC";
const D = "KC-DDDDDD";

describe("constants", () => {
  it("names the cookie and bounds it", () => {
    expect(CHECKOUT_COOKIE).toBe("cb_checkout");
    expect(MAX_CHECKOUTS).toBe(3);
  });
});

describe("isReference", () => {
  it.each([A, "KC-7Q4M2X", "KC-0123ZZ"])("accepts %s", (value) => {
    expect(isReference(value)).toBe(true);
  });

  it.each([
    "",
    "KC-ABC",
    "KC-AAAAAAA",
    "kc-aaaaaa",
    "KC-IIIIII",
    "KC-AAAAAU",
    "X KC-AAAAAA",
    1,
    null,
    [A],
  ])("rejects %j", (value) => {
    expect(isReference(value)).toBe(false);
  });
});

describe("parseCheckouts", () => {
  it("reads entries newest first", () => {
    expect(parseCheckouts(`${A}.cs_x|${B}.cs_test_y`)).toEqual([
      { reference: A, sessionId: "cs_x" },
      { reference: B, sessionId: "cs_test_y" },
    ]);
  });

  it("reads a legacy bare session ID as an entry with no reference", () => {
    expect(parseCheckouts("cs_test_abc")).toEqual([{ reference: null, sessionId: "cs_test_abc" }]);
  });

  it("drops malformed parts", () => {
    expect(
      parseCheckouts(
        `junk|${A}.cs_x|KC-BAD.cs_y|${B}.nope|${C}.|.cs_z|${D}.cs_a.b|cs_|cs_x y|${B}.cs_ok`,
      ),
    ).toEqual([
      { reference: A, sessionId: "cs_x" },
      { reference: B, sessionId: "cs_ok" },
    ]);
  });

  it.each([undefined, "", "|", "garbage"])("returns no entries for %j", (value) => {
    expect(parseCheckouts(value)).toEqual([]);
  });

  it("keeps at most MAX_CHECKOUTS entries", () => {
    expect(parseCheckouts(`${A}.cs_a|${B}.cs_b|${C}.cs_c|${D}.cs_d`)).toHaveLength(3);
  });
});

describe("addCheckout", () => {
  it("starts a cookie from nothing", () => {
    expect(addCheckout(undefined, { reference: A, sessionId: "cs_a" })).toBe(`${A}.cs_a`);
  });

  it("prepends the new entry", () => {
    expect(addCheckout(`${A}.cs_a`, { reference: B, sessionId: "cs_b" })).toBe(
      `${B}.cs_b|${A}.cs_a`,
    );
  });

  it("drops an older entry with the same reference", () => {
    expect(addCheckout(`${A}.cs_a|${B}.cs_b`, { reference: B, sessionId: "cs_b2" })).toBe(
      `${B}.cs_b2|${A}.cs_a`,
    );
  });

  it("drops an older entry with the same session", () => {
    expect(addCheckout(`${A}.cs_a|${B}.cs_b`, { reference: C, sessionId: "cs_a" })).toBe(
      `${C}.cs_a|${B}.cs_b`,
    );
  });

  it("keeps the newest MAX_CHECKOUTS", () => {
    expect(addCheckout(`${C}.cs_c|${B}.cs_b|${A}.cs_a`, { reference: D, sessionId: "cs_d" })).toBe(
      `${D}.cs_d|${C}.cs_c|${B}.cs_b`,
    );
  });

  it("builds on a legacy value, which stays readable", () => {
    const value = addCheckout("cs_old", { reference: A, sessionId: "cs_a" });
    expect(value).toBe(`${A}.cs_a|cs_old`);
    expect(parseCheckouts(value)).toEqual([
      { reference: A, sessionId: "cs_a" },
      { reference: null, sessionId: "cs_old" },
    ]);
  });

  it("drops a malformed value", () => {
    expect(addCheckout("junk", { reference: A, sessionId: "cs_a" })).toBe(`${A}.cs_a`);
  });
});

describe("pickCheckout", () => {
  const two = `${B}.cs_b|${A}.cs_a`;

  it("picks the entry matching ref", () => {
    expect(pickCheckout(two, A)).toBe("cs_a");
    expect(pickCheckout(two, B)).toBe("cs_b");
  });

  it("picks nothing for a valid ref that no entry has, never another entry", () => {
    expect(pickCheckout(two, C)).toBeUndefined();
  });

  it("falls back to a legacy entry for a valid but unknown ref", () => {
    expect(pickCheckout("cs_old", A)).toBe("cs_old");
    expect(pickCheckout(`${B}.cs_b|cs_old`, A)).toBe("cs_old");
  });

  it("picks the newest entry without a ref", () => {
    expect(pickCheckout(two, undefined)).toBe("cs_b");
    expect(pickCheckout("cs_old", undefined)).toBe("cs_old");
  });

  it.each(["", "KC-BAD", "kc-aaaaaa", `${A}x`, 42])(
    "picks the newest for malformed ref %j",
    (ref) => {
      expect(pickCheckout(two, ref)).toBe("cs_b");
    },
  );

  it("picks the newest for an array ref", () => {
    expect(pickCheckout(two, [A, B])).toBe("cs_b");
  });

  it("picks nothing without a cookie", () => {
    expect(pickCheckout(undefined, A)).toBeUndefined();
    expect(pickCheckout(undefined, undefined)).toBeUndefined();
    expect(pickCheckout("junk", undefined)).toBeUndefined();
  });
});
