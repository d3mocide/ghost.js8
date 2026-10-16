// Render the PWA / favicon rasters from public/favicon.svg (the single source of the mark).
// Run: npm run icons   (needs Chromium: `npx playwright install chromium`, or the Playwright image)
// Output is committed; rerun it only when favicon.svg changes.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const pub = new URL('../public/', import.meta.url);
const svg = await readFile(new URL('favicon.svg', pub), 'utf8');

const defs = svg.match(/<defs>[\s\S]*<\/defs>/)?.[0];
const body = svg.match(/<\/defs>([\s\S]*)<\/svg>/)?.[1];
const tile = body?.match(/<rect[^>]*rx="14"[^>]*\/>/)?.[0];
if (!defs || !body || !tile) throw new Error('favicon.svg no longer has the expected structure');
const art = body.replace(tile, '');

/** The mark on a tile. `scale` shrinks the art about the centre (safe zones). */
function variant(tileEl, scale, size) {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="${size}" height="${size}">` +
    `${defs}${tileEl}<g transform="translate(32 32) scale(${scale}) translate(-32 -32)">${art}</g></svg>`
  );
}

const rounded = tile; // "any" icons keep the rounded tile and transparent corners
const fullBleed = tile.replace('rx="14"', 'rx="0"'); // iOS and maskable add their own shape

const jobs = [
  // name, svg tile, art scale, size
  ['icons/icon-192.png', rounded, 1, 192],
  ['icons/icon-512.png', rounded, 1, 512],
  ['icons/icon-maskable-512.png', fullBleed, 0.78, 512], // art inside the 80% safe circle
  ['apple-touch-icon.png', fullBleed, 0.9, 180], // iOS rounds it and fills transparency with black
  ['icons/favicon-16.png', rounded, 1, 16],
  ['icons/favicon-32.png', rounded, 1, 32],
  ['icons/favicon-48.png', rounded, 1, 48],
];

await mkdir(new URL('icons/', pub), { recursive: true });
const browser = await chromium.launch();
const png = new Map();
try {
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  for (const [name, tileEl, scale, size] of jobs) {
    await page.setViewportSize({ width: size, height: size });
    await page.setContent(
      `<!doctype html><body style="margin:0;background:transparent">${variant(tileEl, scale, size)}</body>`,
    );
    const buf = await page.screenshot({
      omitBackground: true,
      clip: { x: 0, y: 0, width: size, height: size },
    });
    await writeFile(new URL(name, pub), buf);
    png.set(name, buf);
    console.log(`wrote public/${name} (${size}x${size}, ${buf.length} bytes)`);
  }
} finally {
  await browser.close();
}

// favicon.ico: three PNG-compressed images (16, 32, 48), for browsers that ask for /favicon.ico.
const sizes = [16, 32, 48];
const images = sizes.map((s) => png.get(`icons/favicon-${String(s)}.png`));
const head = Buffer.alloc(6 + 16 * sizes.length);
head.writeUInt16LE(0, 0); // reserved
head.writeUInt16LE(1, 2); // type: icon
head.writeUInt16LE(sizes.length, 4);
let offset = head.length;
sizes.forEach((s, i) => {
  const entry = 6 + 16 * i;
  head.writeUInt8(s, entry); // width
  head.writeUInt8(s, entry + 1); // height
  head.writeUInt8(0, entry + 2); // palette
  head.writeUInt8(0, entry + 3); // reserved
  head.writeUInt16LE(1, entry + 4); // planes
  head.writeUInt16LE(32, entry + 6); // bits per pixel
  head.writeUInt32LE(images[i].length, entry + 8);
  head.writeUInt32LE(offset, entry + 12);
  offset += images[i].length;
});
await writeFile(new URL('favicon.ico', pub), Buffer.concat([head, ...images]));
console.log(`wrote public/favicon.ico (${sizes.join(', ')})`);
