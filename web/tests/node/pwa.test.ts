import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

// The web app manifest and icons make "Install app" / "Add to Home Screen" show the ghost,
// not a generic tile. These tests read the files exactly as they are shipped.

const pub = (name: string): URL => new URL(`../../public/${name}`, import.meta.url);
const html = readFileSync(new URL('../../index.html', import.meta.url), 'utf8');

interface Icon {
  src: string;
  sizes: string;
  type: string;
  purpose?: string;
}
interface Manifest {
  id: string;
  name: string;
  short_name: string;
  start_url: string;
  scope: string;
  display: string;
  background_color: string;
  theme_color: string;
  icons: Icon[];
}
const manifest = JSON.parse(readFileSync(pub('manifest.webmanifest'), 'utf8')) as Manifest;

/** Width and height from a PNG's IHDR chunk (and the 8-byte signature check). */
function pngSize(buf: Buffer): { w: number; h: number } {
  expect(buf.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
  return { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) };
}
const file = (src: string): Buffer => readFileSync(pub(src.replace(/^\//, '')));

describe('web app manifest', () => {
  it('has what browsers require to offer installation', () => {
    expect(manifest.name).toBe('ghost.js8');
    expect(manifest.short_name.length).toBeLessThanOrEqual(12);
    expect(manifest.display).toBe('standalone');
    expect(manifest.start_url.startsWith(manifest.scope)).toBe(true);
    expect(manifest.id).toBe('/');
  });

  it('declares icons that exist and really have the declared size', () => {
    const raster = manifest.icons.filter((i) => i.type === 'image/png');
    expect(raster.length).toBeGreaterThanOrEqual(3);
    for (const icon of raster) {
      const { w, h } = pngSize(file(icon.src));
      expect(`${String(w)}x${String(h)}`, icon.src).toBe(icon.sizes);
    }
    for (const icon of manifest.icons) expect(file(icon.src).length, icon.src).toBeGreaterThan(100);
  });

  it('has the 192 and 512 icons Chrome needs, and a separate maskable one', () => {
    const sizes = manifest.icons
      .filter((i) => (i.purpose ?? 'any') === 'any' && i.type === 'image/png')
      .map((i) => i.sizes);
    expect(sizes).toEqual(expect.arrayContaining(['192x192', '512x512']));
    const maskable = manifest.icons.filter((i) => i.purpose === 'maskable');
    expect(maskable).toHaveLength(1);
    // never mix purposes ("any maskable"): a crop-safe icon looks small as a plain one
    expect(manifest.icons.some((i) => i.purpose?.includes(' '))).toBe(false);
  });

  it('uses the same colours as the page', () => {
    const theme = /<meta\s+name="theme-color"\s+content="([^"]+)"/.exec(html)?.[1];
    expect(manifest.theme_color).toBe(theme);
    expect(manifest.background_color).toMatch(/^#[0-9a-f]{6}$/i);
  });
});

describe('index.html icon and PWA links', () => {
  it('links the manifest with credentials (the app sits behind an authenticating proxy)', () => {
    const link = /<link\s+rel="manifest"[^>]*>/.exec(html)?.[0] ?? '';
    expect(link).toContain('href="/manifest.webmanifest"');
    expect(link).toContain('crossorigin="use-credentials"');
  });

  it('links every favicon variant and the iOS touch icon, and each file exists', () => {
    const hrefs = [
      ...html.matchAll(/<link\s+rel="(?:icon|apple-touch-icon)"[^>]*href="([^"]+)"/g),
    ].map((m) => m[1] ?? '');
    expect(hrefs).toEqual(
      expect.arrayContaining([
        '/favicon.svg',
        '/favicon.ico',
        '/icons/favicon-32.png',
        '/apple-touch-icon.png',
      ]),
    );
    for (const href of hrefs) expect(file(href).length, href).toBeGreaterThan(100);
  });

  it('gives iOS a 180x180 touch icon and standalone meta tags', () => {
    expect(pngSize(file('/apple-touch-icon.png'))).toEqual({ w: 180, h: 180 });
    expect(html).toContain('name="apple-mobile-web-app-capable"');
    expect(html).toContain('name="mobile-web-app-capable"');
    expect(html).toContain('name="apple-mobile-web-app-title" content="ghost.js8"');
  });
});

describe('favicon.ico', () => {
  it('is a real ICO holding 16, 32 and 48 px images', () => {
    const ico = file('/favicon.ico');
    expect(ico.readUInt16LE(0)).toBe(0); // reserved
    expect(ico.readUInt16LE(2)).toBe(1); // type: icon
    const count = ico.readUInt16LE(4);
    const sizes: number[] = [];
    for (let i = 0; i < count; i += 1) {
      const entry = 6 + 16 * i;
      sizes.push(ico.readUInt8(entry));
      const length = ico.readUInt32LE(entry + 8);
      const offset = ico.readUInt32LE(entry + 12);
      pngSize(ico.subarray(offset, offset + length)); // each image is a valid PNG
    }
    expect(sizes).toEqual([16, 32, 48]);
  });
});
