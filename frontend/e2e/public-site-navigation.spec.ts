import { test, expect } from "@playwright/test";

// PROJECT_PLAN.md Phase 10.5: "Playwright E2E for ... the public site
// navigation." Covers only the unauthenticated marketing site here; the
// three canonical onboarding/decision journeys and login-with-MFA need a
// live backend + seeded data and are out of scope for this static-build
// Playwright run (see e2e/console-login.spec.ts for the shape that would
// take, once run against a full stack).

test("home page loads and links to the core pages", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /onboard customers with confidence/i })).toBeVisible();

  const primaryNav = page.getByRole("navigation", { name: "Primary" });
  await primaryNav.getByRole("link", { name: "Solutions" }).click();
  await expect(page).toHaveURL(/\/solutions$/);
  await expect(page.getByRole("heading", { name: "Solutions", exact: true })).toBeVisible();

  await primaryNav.getByRole("link", { name: "Trust Center" }).click();
  await expect(page).toHaveURL(/\/trust$/);
  await expect(page.getByRole("heading", { name: "Trust Center" })).toBeVisible();
});

test("sign in link reaches the login page", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in" }).first().click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});

test("unknown route falls back to the 404 page", async ({ page }) => {
  await page.goto("/this-route-does-not-exist");
  await expect(page.getByText("Page not found")).toBeVisible();
});

test("cookie consent banner can be accepted and does not reappear", async ({ page }) => {
  await page.goto("/");
  const banner = page.getByText(/we use cookies/i);
  await expect(banner).toBeVisible();
  await page.getByRole("button", { name: "Accept" }).click();
  await expect(banner).not.toBeVisible();

  await page.reload();
  await expect(page.getByText(/we use cookies/i)).not.toBeVisible();
});
