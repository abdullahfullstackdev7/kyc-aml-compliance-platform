import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

// PROJECT_PLAN.md Phase 10.5: "axe accessibility checks in Playwright."
// Checks the pages that exist in this build's scoped Phase 7 catalog.

const PAGES = ["/", "/solutions", "/trust", "/contact", "/login"];

for (const path of PAGES) {
  test(`no critical or serious axe violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa"])
      .analyze();

    const seriousOrWorse = results.violations.filter((v) =>
      ["critical", "serious"].includes(v.impact ?? ""),
    );

    expect(
      seriousOrWorse,
      seriousOrWorse.map((v) => `${v.id}: ${v.description}\n${v.helpUrl}`).join("\n\n"),
    ).toEqual([]);
  });
}
