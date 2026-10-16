import { describe, expect, it } from 'vitest';
import {
  classify,
  countdown,
  netIdFromHash,
  receiverLabel,
  sameReceiver,
  settingsMessage,
  windowWhen,
} from '../../src/lib/ghostnet';

describe('classify', () => {
  it('flags flash traffic', () => {
    expect(classify('W1GHZ: @GSTFLASH BRIDGE OUT ON I-95').flash).toBe(true);
    expect(classify('W1GHZ: @gstflash test').flash).toBe(true);
    expect(classify('W1GHZ: NOT@GSTFLASHY').flash).toBe(false);
  });

  it('recognises GhostNet and regional groups', () => {
    expect(classify('K0OG: @GHOSTNET QSL').ghostnet).toBe(true);
    const sc = classify('KN4CRD: @GNUSASC CHECKING IN');
    expect([sc.ghostnet, sc.regional]).toEqual([true, '@GNUSASC']);
    expect(classify('K0OG: KN4CRD SNR +02')).toEqual({
      flash: false,
      ghostnet: false,
      regional: null,
    });
  });
});

describe('countdown', () => {
  it('formats durations', () => {
    expect(countdown(0, 45_000)).toBe('45s');
    expect(countdown(0, 725_000)).toBe('12m 05s');
    expect(countdown(0, 7_500_000)).toBe('2h 05m');
    expect(countdown(0, 3 * 86400_000 + 4 * 3600_000)).toBe('3d 04h');
    expect(countdown(10, 0)).toBe('0s');
  });
});

describe('netIdFromHash', () => {
  it('accepts bridge-generated ids only', () => {
    expect(netIdFromHash('#/nets/na-net-20261009T0100Z')).toBe('na-net-20261009T0100Z');
    expect(netIdFromHash('#/nets/../../etc')).toBeNull();
    expect(netIdFromHash('#/nets/')).toBeNull();
    expect(netIdFromHash('#/other')).toBeNull();
  });
});

describe('windowWhen', () => {
  it('shows the weekly UTC slot', () => {
    expect(windowWhen({ weekday: 4, start: '01:00', minutes: 30 })).toBe('Fri 01:00–01:30Z');
    expect(windowWhen({ weekday: 5, start: '18:00', minutes: 60 })).toBe('Sat 18:00–19:00Z');
    expect(windowWhen({ weekday: 0, start: '07:05', minutes: 55 })).toBe('Mon 07:05–08:00Z');
  });

  it('wraps an end that falls on the next day', () => {
    expect(windowWhen({ weekday: 6, start: '23:45', minutes: 30 })).toBe('Sun 23:45–00:15Z');
  });
});

describe('receiverLabel / sameReceiver', () => {
  it('prefers the name and falls back to host:port', () => {
    expect(receiverLabel({ host: 'kiwi.example', port: 8073, name: 'W8BUG Knoxville' })).toBe(
      'W8BUG Knoxville',
    );
    expect(receiverLabel({ host: 'kiwi.example', port: 8073, name: null })).toBe(
      'kiwi.example:8073',
    );
    expect(receiverLabel({ host: 'kiwi.example', port: 8073, name: '  ' })).toBe(
      'kiwi.example:8073',
    );
  });

  it('compares by host and port only', () => {
    const a = { host: 'kiwi.example', port: 8073 };
    expect(sameReceiver(a, { ...a, port: 8073 })).toBe(true);
    expect(sameReceiver(a, { host: 'kiwi.example', port: 8074 })).toBe(false);
    expect(sameReceiver(a, null)).toBe(false);
    expect(sameReceiver(undefined, null)).toBe(false);
  });
});

describe('settingsMessage', () => {
  it('sends null for everything the change does not mention', () => {
    expect(settingsMessage({ park: false })).toEqual({
      v: 1,
      type: 'ghostnet_settings',
      autopilot_enabled: null,
      park: false,
      record_audio: null,
      windows: {},
    });
  });

  it('builds complete per-window updates', () => {
    const rx = { host: 'kiwi.example', port: 8073, name: 'K', tls: false };
    const msg = settingsMessage({
      autopilotEnabled: true,
      recordAudio: false,
      windows: {
        'na-net': { enabled: false },
        'na-eu-20m': { receiver: rx },
        'na-aus-20m': { clearReceiver: true },
      },
    });
    expect(msg.autopilot_enabled).toBe(true);
    expect(msg.record_audio).toBe(false);
    expect(msg.windows['na-net']).toEqual({
      enabled: false,
      receiver: null,
      clear_receiver: false,
    });
    expect(msg.windows['na-eu-20m']).toEqual({
      enabled: null,
      receiver: rx,
      clear_receiver: false,
    });
    expect(msg.windows['na-aus-20m']).toEqual({
      enabled: null,
      receiver: null,
      clear_receiver: true,
    });
  });
});
