import type { Locator, Page } from "@playwright/test";

export async function selectHostTheme(
  page: Page,
  theme: "Light" | "Dark" | "System",
) {
  await page.getByTestId("stMainMenu").click();
  await page.getByRole("menuitemradio", { name: theme, exact: true }).click();
  await page.keyboard.press("Escape");
}

export async function imagePixel(svg: Locator) {
  return svg.evaluate(async (element) => {
    const href = element.querySelector("image")!.getAttribute("href")!;
    const [x, y, width, height] = element
      .getAttribute("viewBox")!
      .split(/\s+/u)
      .map(Number);
    const image = new Image();
    image.src = href;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const ctx = canvas.getContext("2d")!;
    ctx.drawImage(image, x + width * 0.2, y + height * 0.5, 1, 1, 0, 0, 1, 1);
    return [...ctx.getImageData(0, 0, 1, 1).data];
  });
}
