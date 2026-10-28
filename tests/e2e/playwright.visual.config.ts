import { devices } from "@playwright/test";
import { featureConfig } from "./feature-config";

// Baselines are rendered inside the pinned Playwright Linux image; see
// update_visual_baselines.py. Other platforms skip the suite.
const config = featureConfig("visual", 8521, [
  { name: "mobile", grep: /@mobile/, use: { ...devices["Pixel 7"] } },
]);

export default {
  ...config,
  snapshotPathTemplate: "{testDir}/__screenshots__/{projectName}/{arg}{ext}",
  expect: {
    toHaveScreenshot: { animations: "disabled", caret: "hide" },
  },
};
