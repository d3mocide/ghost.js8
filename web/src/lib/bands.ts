/** JS8 calling frequencies: JS8Call 3.0.3 defaults (JS8_Main/FrequencyList.cpp). Dial, USB. */
export interface BandPreset {
  readonly band: string;
  readonly dialHz: number;
}

export const JS8_BANDS: readonly BandPreset[] = [
  { band: '160m', dialHz: 1_843_500 },
  { band: '80m', dialHz: 3_578_000 },
  { band: '60m', dialHz: 5_363_000 },
  { band: '40m', dialHz: 7_078_000 },
  { band: '30m', dialHz: 10_130_000 },
  { band: '20m', dialHz: 14_078_000 },
  { band: '17m', dialHz: 18_104_000 },
  { band: '15m', dialHz: 21_078_000 },
  { band: '12m', dialHz: 24_922_000 },
  { band: '10m', dialHz: 28_078_000 },
  { band: '6m', dialHz: 50_318_000 },
];

export function bandFor(dialHz: number): string | null {
  return JS8_BANDS.find((b) => Math.abs(b.dialHz - dialHz) < 50_000)?.band ?? null;
}
