import { devices } from "@playwright/test";
import { featureConfig } from "./feature-config";

// Phone-width coverage runs only the specs tagged @mobile.
export default featureConfig("interaction", 8520, [
  { name: "mobile", grep: /@mobile/, use: { ...devices["Pixel 7"] } },
]);
