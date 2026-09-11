import { test, expect } from "@playwright/test";
import { waitForGalleryStable } from "../tests/harness";

test("full membership survives partial expansion, budget changes, and collapse",async({page})=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.goto("/");await waitForGalleryStable(page);
  const marker=page.locator('.sgc-group-marker');
  const host=page.locator('[data-sgc-status="ready"]');
  await expect(marker).toHaveText("30");
  await expect(host).toHaveAttribute("data-sgc-rendered-elements","3");
  await marker.press("Enter");await waitForGalleryStable(page);
  await expect(marker).toHaveText("9 / 30");
  await expect(page.locator('.sgc-group-header')).toHaveText("Members · 9 of 30");
  await expect(host).toHaveAttribute("data-sgc-rendered-elements","20");
  await expect(page.locator('.sgc-budget-notice')).toContainText("21 nodes");
  const budget=page.getByRole("spinbutton",{name:"Display budget"});
  await budget.fill("100");await budget.press("Enter");await waitForGalleryStable(page);
  await expect(marker).toHaveText("30");
  await expect(host).toHaveAttribute("data-sgc-rendered-elements","62");
  await expect(page.locator('.sgc-budget-notice')).toHaveCount(0);
  await marker.press("Enter");await waitForGalleryStable(page);
  await expect(host).toHaveAttribute("data-sgc-rendered-elements","3");
  await expect(marker).toHaveText("30");
  expect(errors).toEqual([]);
});
