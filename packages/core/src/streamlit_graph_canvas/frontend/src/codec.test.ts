import { describe, expect, it } from "vitest";
import { CODEC_VERSION } from "./contract";
import { requireCodecVersion } from "./codec";

describe("canvas codec", () => {
  it("accepts only the generated codec version", () => {
    expect(() => requireCodecVersion(CODEC_VERSION)).not.toThrow();
    expect(() => requireCodecVersion(CODEC_VERSION + 1)).toThrow(
      "SGC_CODEC_VERSION",
    );
  });
});
