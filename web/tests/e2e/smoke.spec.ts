import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test.describe('ghost.js8 smoke', () => {
  test('establishes the link and shows live traffic', async ({ page, isMobile }) => {
    await page.goto('/');
    await expect(page.getByTestId('link-state')).toContainText('LINK ESTABLISHED');
    await expect(page.getByTestId('mode-chip')).toHaveText(/\bRX\b/);
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

  test('is installable as an app: manifest, icons and favicons are served', async ({ page }) => {
    await page.goto('/');
    const href = await page.locator('link[rel="manifest"]').getAttribute('href');
    expect(href).toBe('/manifest.webmanifest');
    const res = await page.request.get(href ?? '');
    expect(res.status()).toBe(200);
    const manifest = (await res.json()) as { name: string; icons: { src: string; type: string }[] };
    expect(manifest.name).toBe('ghost.js8');
    for (const icon of manifest.icons) {
      const r = await page.request.get(icon.src);
      expect(r.status(), icon.src).toBe(200);
      expect(r.headers()['content-type'], icon.src).toContain(icon.type);
    }
    for (const path of ['/favicon.ico', '/apple-touch-icon.png', '/icons/favicon-32.png']) {
      expect((await page.request.get(path)).status(), path).toBe(200);
    }
  });

  // Not Page.getInstallabilityErrors: headless Chromium returns [] even for a manifest with no
  // icons, so it proves nothing. What can be checked is that the browser found and parsed ours.
  test('Chromium finds and parses the manifest without errors', async ({ page, context }) => {
    await page.goto('/');
    await expect(page.getByTestId('link-state')).toContainText('LINK ESTABLISHED');
    const cdp = await context.newCDPSession(page);
    const mf = (await cdp.send('Page.getAppManifest')) as {
      url?: string;
      errors: unknown[];
      data?: string;
    };
    expect(mf.url ?? '').toContain('/manifest.webmanifest');
    expect(mf.errors).toEqual([]);
    const parsed = JSON.parse(mf.data ?? '{}') as { name?: string; icons?: unknown[] };
    expect(parsed.name).toBe('ghost.js8');
    expect(parsed.icons?.length ?? 0).toBeGreaterThanOrEqual(3);
  });

  test('has no transmit control anywhere', async ({ page, isMobile }) => {
    await page.goto('/');
    await expect(page.getByTestId('link-state')).toContainText('LINK ESTABLISHED');
    const views = isMobile ? ['Traffic', 'Waterfall', 'Stations', 'Map', 'Status'] : [''];
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
    if (isMobile) await page.getByRole('button', { name: 'Waterfall', exact: true }).click();
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

  test('backdrop is decorative and can be switched to a still gradient', async ({ page }) => {
    await page.goto('/');
    const fx = page.getByRole('button', { name: 'Animated backdrop' });
    await expect(fx).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('backdrop')).toHaveAttribute('aria-hidden', 'true');
    await fx.click();
    await expect(fx).toHaveAttribute('aria-pressed', 'false');
    await expect(page.getByTestId('backdrop')).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole('button', { name: 'Animated backdrop' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });
});
