import { expect, test } from "@playwright/test";

test.describe("Model Selector", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("displays a model button", async ({ page }) => {
    await expect(page.getByTestId("model-selector")).toBeVisible();
  });

  test("opens model selector popover on click", async ({ page }) => {
    await page.getByTestId("model-selector").click();

    await expect(page.getByPlaceholder("Search models...")).toBeVisible();
  });

  test("can search for models", async ({ page }) => {
    await page.getByTestId("model-selector").click();

    const searchInput = page.getByPlaceholder("Search models...");
    await searchInput.fill("Mimo");

    await expect(page.getByText("Mimo V2.5 Pro").first()).toBeVisible();
    await expect(page.getByText("GLM")).not.toBeVisible();
  });

  test("can close model selector by clicking outside", async ({ page }) => {
    await page.getByTestId("model-selector").click();

    await expect(page.getByPlaceholder("Search models...")).toBeVisible();

    await page.keyboard.press("Escape");

    await expect(page.getByPlaceholder("Search models...")).not.toBeVisible();
  });

  test("shows model provider groups", async ({ page }) => {
    await page.getByTestId("model-selector").click();

    await expect(page.getByText("Available")).toBeVisible();
    await expect(page.getByText("Mimo V2.5 Pro").nth(1)).toBeVisible();
    await expect(page.getByText("Mistral Small")).not.toBeVisible();
  });

  test("can select the Mimo model", async ({ page }) => {
    await page.getByTestId("model-selector").click();

    await page.getByText("Mimo V2.5 Pro").first().click();

    await expect(page.getByPlaceholder("Search models...")).not.toBeVisible();

    await expect(page.getByTestId("model-selector")).toContainText(
      "Mimo V2.5 Pro"
    );
  });
});
