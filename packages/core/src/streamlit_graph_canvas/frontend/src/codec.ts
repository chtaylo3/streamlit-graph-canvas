import { CODEC_VERSION } from "./contract";

export function requireCodecVersion(value: unknown): void {
  if (value !== CODEC_VERSION) {
    throw new Error(
      `SGC_CODEC_VERSION: expected ${CODEC_VERSION}; received ${String(value)}`,
    );
  }
}
