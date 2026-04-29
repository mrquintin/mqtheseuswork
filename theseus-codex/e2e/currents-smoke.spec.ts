import { expect, test } from "@playwright/test";

test("currents feed renders, detail page works, follow-up streams", async ({ page }) => {
  await page.goto("/currents");
  await expect(page.getByText(/live|reconnecting/i)).toBeVisible();

  const firstCard = page.locator("article").first();
  await expect(firstCard).toBeVisible();
  await firstCard.getByRole("link", { name: /ask a follow-up/i }).click();

  const input = page.getByRole("textbox");
  await input.fill("What is the firm's reasoning?");
  await input.press("Enter");

  const assistantMsg = page.locator('[data-role="assistant"]').last();
  await expect(assistantMsg).not.toBeEmpty({ timeout: 15_000 });
});
