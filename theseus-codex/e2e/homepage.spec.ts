import { expect, test } from "@playwright/test";

test("public homepage explains the institution and exposes bounded currents", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "THESEUS · INTELLECTUAL CAPITAL",
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "A research firm that puts its money where its mind is",
    ),
  ).toBeVisible();

  const currentCards = page.getByTestId("homepage-current-card");
  const currentCount = await currentCards.count();
  expect(currentCount).toBeGreaterThanOrEqual(0);
  expect(currentCount).toBeLessThanOrEqual(3);

  await page.getByRole("link", { name: "About →" }).click();
  await expect(page).toHaveURL(/\/about(?:[#?].*)?$/);

  await page.getByRole("link", { name: "Manifesto" }).click();
  await expect(page).toHaveURL(/\/about#manifesto$/);
  await expect(page.locator("#manifesto")).toBeVisible();
});
