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

  // The settings live in the bridge and are shared by every viewer, and the desktop and phone
  // projects run in parallel against one stack. So only the desktop project changes them
  // (and puts them back); the phone project just checks the layout.
  async function openSettings(
    page: import('@playwright/test').Page,
    isMobile: boolean,
  ): Promise<void> {
    await page.goto('/');
    if (isMobile) await page.getByRole('button', { name: 'GhostNet', exact: true }).click();
    const settings = page.getByTestId('gn-settings');
    await expect(settings).toBeVisible({ timeout: 20_000 });
    if (!(await settings.evaluate((el: HTMLDetailsElement) => el.open))) {
      await settings.locator('summary').click();
    }
  }

  test('autopilot settings list the plan with its UTC slots', async ({ page, isMobile }) => {
    await openSettings(page, isMobile);
    const net = page.getByTestId('gn-window-na-net');
    await expect(net).toContainText('GhostNet North America');
    await expect(net).toContainText('Fri 01:00–01:30Z');
    await expect(net).toContainText('40m');
    await expect(page.getByTestId('gn-window-na-eu-20m')).toContainText('Sat 18:00–19:00Z');
    await expect(page.getByTestId('gn-settings')).toContainText(/\d+\/\d+ nets followed/);
  });

  test.describe('changing autopilot settings', () => {
    test.beforeEach(({ isMobile }) => {
      test.skip(isMobile, 'settings are shared by every viewer; desktop changes them');
    });

    test.afterEach(async ({ page, isMobile }) => {
      if (isMobile) return;
      await openSettings(page, isMobile);
      const follow = page.getByTestId('gn-follow-na-net');
      if (!(await follow.isChecked())) await follow.click();
      await expect(follow).toBeChecked();
      const auto = page.getByTestId('gn-autopilot');
      if (!(await auto.isChecked())) await auto.click();
      await expect(auto).toBeChecked();
      const clear = page.getByRole('button', { name: /Back to automatic receiver for/ });
      while ((await clear.count()) > 0) await clear.first().click();
    });

    test('a net can be switched off, and it stays off after a reload', async ({
      page,
      isMobile,
    }) => {
      await openSettings(page, isMobile);
      const follow = page.getByTestId('gn-follow-na-net');
      await expect(follow).toBeChecked();
      await follow.click();
      await expect(follow).not.toBeChecked();
      await expect(page.getByTestId('gn-window-na-net')).toHaveClass(/off/);
      await openSettings(page, isMobile); // fresh page: state comes back from the bridge
      await expect(page.getByTestId('gn-follow-na-net')).not.toBeChecked();
    });

    test('the master switch greys out the rest and shows the autopilot as off', async ({
      page,
      isMobile,
    }) => {
      await openSettings(page, isMobile);
      await page.getByTestId('gn-autopilot').click();
      await expect(page.getByTestId('panel-ghostnet')).toContainText('AUTOPILOT OFF');
      await expect(page.getByTestId('gn-park')).toBeDisabled();
      await expect(page.getByTestId('gn-follow-na-net')).toBeDisabled();
      await page.getByTestId('gn-autopilot').click();
      await expect(page.getByTestId('gn-park')).toBeEnabled();
    });

    test('the receiver in use can be preferred for a net, then cleared', async ({
      page,
      isMobile,
    }) => {
      await openSettings(page, isMobile);
      const pin = page.getByTestId('gn-pin-na-eu-20m');
      await expect(pin).toBeVisible({ timeout: 30_000 }); // needs a connected receiver
      await pin.click();
      await expect(page.getByTestId('gn-pref-na-eu-20m')).toBeVisible();
      await expect(page.getByTestId('gn-window-na-eu-20m')).toContainText('Prefers');
      await page.getByRole('button', { name: /Back to automatic receiver for .*Europe/ }).click();
      await expect(page.getByTestId('gn-pref-na-eu-20m')).toBeHidden();
      await expect(page.getByTestId('gn-window-na-eu-20m')).toContainText('best available');
    });
  });
});
