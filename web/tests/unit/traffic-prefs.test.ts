import { describe, expect, it } from 'vitest';
import { DEFAULT_TRAFFIC_PREFS, parseTrafficPrefs } from '../../src/lib/traffic-prefs';

describe('parseTrafficPrefs', () => {
  it('defaults to directed messages only, unthreaded', () => {
    expect(DEFAULT_TRAFFIC_PREFS).toEqual({ directedOnly: true, threaded: false });
    expect(parseTrafficPrefs(null)).toEqual(DEFAULT_TRAFFIC_PREFS);
  });

  it('restores a saved choice, including showing everything', () => {
    expect(parseTrafficPrefs('{"directedOnly":false,"threaded":true}')).toEqual({
      directedOnly: false,
      threaded: true,
    });
  });

  it('falls back per field on junk', () => {
    expect(parseTrafficPrefs('not json')).toEqual(DEFAULT_TRAFFIC_PREFS);
    expect(parseTrafficPrefs('[1,2]')).toEqual(DEFAULT_TRAFFIC_PREFS);
    expect(parseTrafficPrefs('{"directedOnly":"yes","threaded":true}')).toEqual({
      directedOnly: true,
      threaded: true,
    });
  });
});
