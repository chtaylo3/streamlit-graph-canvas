import { describe, expect, it } from "vitest";
import { tone } from "./palette";

describe("palette tones", () => {
  it("uses CSS theme-aware light-dark colors", () => {
    expect(tone({ accent: { light: "#000", dark: "#fff" } }, "accent"))
      .toBe("light-dark(#000, #fff)");
    expect(tone({}, "missing")).toBe("transparent");
  });
});
