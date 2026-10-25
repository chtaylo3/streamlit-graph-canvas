import { describe, expect, it } from "vitest";
import { resolveHostTheme } from "./host-theme";

describe("host theme selection", () => {
  it.each([false, true])(
    "respects explicit host modes with prefersDark=%s",
    (os) => {
      expect(resolveHostTheme("light", os)).toBe("light");
      expect(resolveHostTheme("dark", os)).toBe("dark");
      expect(resolveHostTheme("only light", os)).toBe("light");
      expect(resolveHostTheme("only dark", os)).toBe("dark");
    },
  );
  it.each(["normal", "light dark", "dark light", "", "custom"])(
    "falls back to OS for %s",
    (scheme) => {
      expect(resolveHostTheme(scheme, false)).toBe("light");
      expect(resolveHostTheme(scheme, true)).toBe("dark");
    },
  );
});
