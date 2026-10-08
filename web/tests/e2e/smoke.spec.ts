import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.describe('ghost.js8 smoke', () => {
  test('establishes the link and shows live traffic', async ({ page, isMobile }) => {
    await page.goto('/');
    await expect(page.getByTestId('link-state')).toContainText('LINK ESTABLISHED');
    await expect(page.getByTestId('decode-row').first()).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId('situation')).toHaveAttribute(
      'data-code',
      /listening|band-quiet/,
    );
    if (isMobile) {
      await page.getByRole('button', { name: 'Stations' }).click();
    }
    await expect(page.getByTestId('station-row').first()).toBeVisible({ timeout: 20_000 });
  });

  test('has no transmit control anywhere', async ({ page, isMobile }) => {
    await page.goto('/');
    await expect(page.getByTestId('link-state')).toContainText('LINK ESTABLISHED');
    const views = isMobile
      ? ['Traffic', 'Waterfall', 'Stations', 'Map', 'Controls', 'Status']
      : [''];
    for (const view of views) {
      if (view) await page.getByRole('button', { name: view, exact: true }).click();
      const controls = page.locator('button, input, select, textarea, [role="button"], a');
      const texts = await controls.evaluateAll((els) =>
        els.map((e) =>
          [
            e.textContent,
            e.getAttribute('aria-label'),
            e.getAttribute('title'),
            e.getAttribute('name'),
            e.getAttribute('placeholder'),
          ]
            .filter(Boolean)
            .join(' ')
            .toLowerCase(),
        ),
      );
      const forbidden = /\b(transmit|tx|send|key ?up|ptt|beacon|heartbeat on|cq)\b/;
      expect(texts.filter((t) => forbidden.test(t))).toEqual([]);
    }
  });

  test('waterfall renders rows', async ({ page, isMobile }) => {
    await page.goto('/');
    if (isMobile) await page.getByRole('button', { name: 'Waterfall', exact: true }).click();
    const canvas = page.getByTestId('waterfall-canvas');
    await expect(canvas).toBeVisible();
    await expect
      .poll(
        () =>
          canvas.evaluate((c: HTMLCanvasElement) => {
            const ctx = c.getContext('2d');
            if (!ctx) return 0;
            const d = ctx.getImageData(0, 0, c.width, Math.min(c.height, 20)).data;
            let lit = 0;
            for (let i = 0; i < d.length; i += 4)
              if ((d[i] ?? 0) + (d[i + 1] ?? 0) + (d[i + 2] ?? 0) > 120) lit++;
            return lit;
          }),
        { timeout: 15_000 },
      )
      .toBeGreaterThan(0);
  });

  test('maps only stations with valid grids', async ({ page, isMobile }) => {
    await page.goto('/');
    if (isMobile) await page.getByRole('button', { name: 'Map', exact: true }).click();
    await expect(page.getByTestId('panel-map')).toContainText(/[1-9] with grid/, {
      timeout: 30_000,
    });
  });

  test('audio monitor starts and stops cleanly', async ({ page, isMobile }) => {
    await page.goto('/');
    if (isMobile) await page.getByRole('button', { name: 'Controls', exact: true }).click();
    const toggle = page.getByTestId('audio-toggle');
    await expect(toggle).toHaveText(/enable audio/i);
    await toggle.click();
    await expect(page.getByTestId('panel-audio')).toContainText(/buffer \d+ ms/, {
      timeout: 10_000,
    });
    await expect(page.getByTestId('panel-audio')).not.toContainText('could not start');
    await toggle.click();
    await expect(toggle).toHaveText(/enable audio/i);
  });

  test('passes an automated accessibility scan', async ({ page }) => {
    // Scan the settled UI: entry animations briefly tint rows.
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/');
    await expect(page.getByTestId('decode-row').first()).toBeVisible({ timeout: 20_000 });
    const results = await new AxeBuilder({ page }).exclude('.maplibregl-canvas').analyze();
    const serious = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );
    expect(
      serious.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`),
    ).toEqual([]);
  });
});
