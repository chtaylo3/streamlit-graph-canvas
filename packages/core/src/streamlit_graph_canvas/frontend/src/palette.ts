export type Palette = Record<string, { light: string; dark?: string }>;

export function tone(palette: Palette, name: string): string {
  const value = palette[name];
  if (!value) return "transparent";
  return value.dark ? `light-dark(${value.light}, ${value.dark})` : value.light;
}
