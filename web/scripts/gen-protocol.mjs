// Generate src/lib/protocol/generated.ts from ../contract/schema.json.
// Run via `make contract`; never edit the output by hand.
import { readFile, writeFile } from 'node:fs/promises';
import { compile } from 'json-schema-to-typescript';

const schemaPath = new URL('../../contract/schema.json', import.meta.url);
const outPath = new URL('../src/lib/protocol/generated.ts', import.meta.url);

const schema = JSON.parse(await readFile(schemaPath, 'utf8'));
const ts = await compile(schema, 'GhostJs8Protocol', {
  bannerComment:
    '/* eslint-disable */\n/**\n * GENERATED from contract/schema.json by web/scripts/gen-protocol.mjs.\n * Source of truth: bridge/src/ghostjs8/contract/messages.py. Do not edit.\n */',
  additionalProperties: false,
  unreachableDefinitions: true,
  strictIndexSignatures: true,
  format: true,
  style: { singleQuote: true, printWidth: 100 },
});
await writeFile(outPath, ts);
console.log(`wrote ${outPath.pathname}`);
