/**
 * One headline that tells the operator what is going on, in plain terms.
 * Distinguishes "the band is quiet" from "something is broken": propagation and
 * public receiver availability are not decoder success or failure.
 */
import type { AppState } from './state';

export type Tone = 'ok' | 'info' | 'warn' | 'alert';

export interface Situation {
  readonly code: string;
  readonly tone: Tone;
  readonly headline: string; // terse, operator-style
  readonly detail: string; // plain-language explanation
  readonly suggestSwitch: boolean; // offer receiver switching
}

const QUIET_AFTER_MS = 5 * 60_000;

export function situation(s: AppState, now: number): Situation {
  if (s.link !== 'open') {
    return {
      code: 'link',
      tone: s.link === 'closed' ? 'alert' : 'warn',
      headline: s.link === 'closed' ? 'LINK CLOSED' : 'ACQUIRING LINK',
      detail: 'No connection to the ghost.js8 bridge. Retrying automatically.',
      suggestSwitch: false,
    };
  }
  const h = s.health;
  const session = s.session;
  if (h && h.components.decoder_process.state !== 'ok') {
    return {
      code: 'decoder-down',
      tone: 'alert',
      headline: 'DECODER OFFLINE',
      detail: `The JS8Call decoder is not running (${h.components.decoder_process.detail || 'no report'}). It restarts automatically; nothing you do in the browser fixes this.`,
      suggestSwitch: false,
    };
  }
  if (!session || session.state === 'idle' || !session.receiver) {
    return {
      code: 'no-receiver',
      tone: 'info',
      headline: 'NO RECEIVER SELECTED',
      detail: 'Pick a public KiwiSDR or enter host:port to start listening.',
      suggestSwitch: false,
    };
  }
  if (session.state === 'rejected') {
    const r = session.reject_reason;
    if (r === 'full') {
      return {
        code: 'receiver-full',
        tone: 'warn',
        headline: 'RECEIVER FULL',
        detail:
          'Every listening slot on this receiver is taken. Retrying politely; another receiver may be free now.',
        suggestSwitch: true,
      };
    }
    if (r === 'busy' || r === 'duplicate_ip') {
      return {
        code: 'receiver-busy',
        tone: 'warn',
        headline: 'RECEIVER BUSY',
        detail: `The receiver refused for now (${session.detail}). Retrying politely.`,
        suggestSwitch: true,
      };
    }
    return {
      code: 'receiver-refused',
      tone: 'alert',
      headline: r === 'auth' ? 'PASSWORD REQUIRED' : 'RECEIVER REFUSED',
      detail: `${session.detail} Not retrying until you choose again.`,
      suggestSwitch: true,
    };
  }
  if (session.state === 'failed') {
    return {
      code: 'receiver-unsupported',
      tone: 'alert',
      headline: 'UNSUPPORTED RECEIVER AUDIO',
      detail: `${session.detail} Choose a different receiver.`,
      suggestSwitch: true,
    };
  }
  if (session.state === 'connecting' || session.state === 'backoff') {
    return {
      code: 'connecting',
      tone: 'warn',
      headline: session.state === 'backoff' ? 'RECEIVER LOST — RETRYING' : 'CONNECTING TO RECEIVER',
      detail: session.detail || 'Opening the receiver session.',
      suggestSwitch: session.state === 'backoff',
    };
  }
  if (s.receiverStatus?.adc_overload) {
    return {
      code: 'adc-overload',
      tone: 'alert',
      headline: 'ADC OVERLOAD AT RECEIVER',
      detail:
        'The remote receiver’s input is overloaded by strong signals. Browser volume cannot fix this, and ghost.js8 will not change someone else’s hardware settings. Decoding may suffer; consider another receiver.',
      suggestSwitch: true,
    };
  }
  if (h && h.components.audio.state === 'down') {
    return {
      code: 'audio-stale',
      tone: 'warn',
      headline: 'AUDIO STALE',
      detail: `Connected, but no fresh audio is arriving from the receiver (${h.components.audio.detail}).`,
      suggestSwitch: true,
    };
  }
  if (
    h &&
    (h.components.decoder_capture.state !== 'ok' || h.components.decoder_api.state !== 'ok')
  ) {
    return {
      code: 'decoder-degraded',
      tone: 'warn',
      headline: 'DECODER DEGRADED',
      detail:
        h.components.decoder_capture.detail ||
        h.components.decoder_api.detail ||
        'Decoder not fully ready.',
      suggestSwitch: false,
    };
  }
  const last = h?.last_decode_utc ? Date.parse(h.last_decode_utc) : null;
  if (last === null || now - last > QUIET_AFTER_MS) {
    return {
      code: 'band-quiet',
      tone: 'info',
      headline: 'NO TRAFFIC — BAND QUIET',
      detail:
        'Receiver and decoder are healthy. No JS8 heard recently: propagation, time of day or simply no activity. This is not a fault.',
      suggestSwitch: false,
    };
  }
  return {
    code: 'listening',
    tone: 'ok',
    headline: 'LISTENING — TRAFFIC COPIED',
    detail: 'Receiver connected, decoder online, decodes arriving.',
    suggestSwitch: false,
  };
}
