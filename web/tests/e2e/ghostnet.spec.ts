import { expect, test } from '@playwright/test';

// The e2e stack runs the GhostNet autopilot (region na, home grid EN34) against
// the simulated receiver, with one seeded recording of last week's net.

test.describe('GhostNet', () => {
  test('autopilot status and recorded nets are shown', async ({ page, isMobile }) => {
    await page.goto('/');
    if (isMobile) await page.getByRole('button', { name: 'GhostNet', exact: true }).click();
    const panel = page.getByTestId('panel-ghostnet');
    await expect(panel).toContainText(/WATCHING 7\.107|ON NET/, { timeout: 20_000 });
    await expect(panel).toContainText('North America');
    await expect(panel).toContainText(/until next net|left on air|on air in/);
    await expect(page.getByTestId('net-link').first()).toContainText('GhostNet North America');
  });

  test('a recorded net replays waterfall, audio and traffic', async ({ page, isMobile }) => {
    await page.goto('/');
    if (isMobile) await page.getByRole('button', { name: 'GhostNet', exact: true }).click();
    await page.getByTestId('net-link').first().click();
    const view = page.getByTestId('net-log');
    await expect(view).toBeVisible();
    await expect(view.getByRole('heading', { name: 'GhostNet North America' })).toBeVisible();
    const img = page.getByTestId('net-waterfall');
    await expect.poll(() => img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBe(400);
    const audio = page.getByTestId('net-audio');
    await expect
      .poll(() => audio.evaluate((el: HTMLAudioElement) => el.duration), { timeout: 15_000 })
      .toBeGreaterThan(200);
    const traffic = page.getByTestId('net-traffic');
    await expect(traffic).toContainText('@GSTFLASH DRILL');
    await expect(traffic.getByText('FLASH', { exact: true })).toBeVisible();
    await expect(traffic.getByText('@GNUSAIN', { exact: true })).toBeVisible();
    await page.getByRole('link', { name: '← LIVE' }).click();
    await expect(view).toBeHidden();
  });

  test('@GSTFLASH traffic raises an alert that can be acknowledged', async ({ page }) => {
    await page.goto('/');
    const alert = page.getByTestId('flash-alert');
    await expect(alert).toBeVisible({ timeout: 30_000 });
    await expect(alert).toContainText('@GSTFLASH');
    await alert.getByRole('button', { name: 'Acknowledge' }).click();
    await expect(alert).toBeHidden();
  });
});
