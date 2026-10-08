/* eslint-disable */
/**
 * GENERATED from contract/schema.json by web/scripts/gen-protocol.mjs.
 * Source of truth: bridge/src/ghostjs8/contract/messages.py. Do not edit.
 */

/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "ServerMessage".
 */
export type ServerMessage =
  Hello | Health | Session | Decode | Station | History | ReceiverStatus | GhostNet | Error | Pong;
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage =
  ClientHello | Tune | SelectReceiver | DisconnectReceiver | Subscribe | Ping;

/**
 * ghost.js8 bridge <-> browser protocol v1. Generated; do not edit.
 */
export interface GhostJs8Protocol {
  server?: ServerMessage;
  client?: ClientMessage;
}
/**
 * First message on every connection.
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Hello".
 */
export interface Hello {
  v: 1;
  type: 'hello';
  server: string;
  build: string;
  receive_only: true;
  limits: Limits | null;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Limits".
 */
export interface Limits {
  max_clients: number;
  audio_sample_rate: number;
  waterfall_max_fps: number;
  waterfall_bins: number;
}
/**
 * Truthful readiness: distinct components, each with evidence timestamps.
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Health".
 */
export interface Health {
  v: 1;
  type: 'health';
  utc: string;
  overall: 'listening' | 'degraded' | 'offline';
  components: Components;
  last_decode_utc: string | null;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Components".
 */
export interface Components {
  bridge: Component;
  decoder_process: Component;
  decoder_api: Component;
  decoder_capture: Component;
  receiver: Component;
  audio: Component;
  waterfall: Component;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Component".
 */
export interface Component {
  state: 'ok' | 'degraded' | 'down' | 'unknown';
  since: string;
  last_seen: string | null;
  detail: string;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Session".
 */
export interface Session {
  v: 1;
  type: 'session';
  state: 'idle' | 'connecting' | 'connected' | 'backoff' | 'rejected' | 'failed';
  receiver: ReceiverRef | null;
  tuning: TuningModel;
  subscribers: number;
  reject_reason: ('full' | 'busy' | 'auth' | 'down' | 'redirect' | 'duplicate_ip') | null;
  detail: string;
  next_retry_utc: string | null;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "ReceiverRef".
 */
export interface ReceiverRef {
  host: string;
  port: number;
  name: string | null;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "TuningModel".
 */
export interface TuningModel {
  dial_hz: number;
  mode: 'usb' | 'lsb';
  low_cut_hz: number;
  high_cut_hz: number;
}
/**
 * One decoded JS8 transmission. ``utc`` comes from the decoder, never inferred.
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Decode".
 */
export interface Decode {
  v: 1;
  type: 'decode';
  kind: 'activity' | 'directed';
  utc: string;
  text: string;
  snr_db: number;
  offset_hz: number;
  dial_hz: number | null;
  freq_hz: number | null;
  speed: string;
  from_call: string | null;
  to_call: string | null;
  grid: string | null;
}
/**
 * A heard station. ``grid`` is present only when it is a valid Maidenhead locator.
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Station".
 */
export interface Station {
  v: 1;
  type: 'station';
  callsign: string;
  last_heard_utc: string;
  snr_db: number | null;
  grid: string | null;
  offset_hz: number | null;
  dial_hz: number | null;
  heard_count: number;
}
/**
 * Sent once after hello: recent traffic from the store, oldest first.
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "History".
 */
export interface History {
  v: 1;
  type: 'history';
  decodes: Decode[];
  stations: Station[];
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "ReceiverStatus".
 */
export interface ReceiverStatus {
  v: 1;
  type: 'receiver_status';
  adc_overload: boolean;
  rssi_dbm: number | null;
  info: {
    [k: string]: string | undefined;
  };
}
/**
 * GhostNet autopilot status (absent features report enabled = false).
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "GhostNet".
 */
export interface GhostNet {
  v: 1;
  type: 'ghostnet';
  enabled: boolean;
  region: ('na' | 'eu' | 'aus') | null;
  home_grid: string | null;
  mode: 'off' | 'window' | 'parked' | 'paused';
  window: GhostNetWindow | null;
  next_window: GhostNetWindow | null;
  recording_net_id: string | null;
  receiver_reason: string;
  paused_until: string | null;
  detail: string;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "GhostNetWindow".
 */
export interface GhostNetWindow {
  id: string;
  label: string;
  kind: 'net' | 'bridge';
  band: string;
  dial_hz: number;
  start: string;
  end: string;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Error".
 */
export interface Error {
  v: 1;
  type: 'error';
  code:
    | 'bad_message'
    | 'unsupported_version'
    | 'session_full'
    | 'invalid_tuning'
    | 'invalid_receiver'
    | 'rate_limited'
    | 'internal';
  message: string;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Pong".
 */
export interface Pong {
  v: 1;
  type: 'pong';
  utc: string;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "ClientHello".
 */
export interface ClientHello {
  v: 1;
  type: 'hello';
  client: string;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Tune".
 */
export interface Tune {
  v: 1;
  type: 'tune';
  tuning: TuningModel;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "SelectReceiver".
 */
export interface SelectReceiver {
  v: 1;
  type: 'select_receiver';
  receiver: ReceiverRef;
  password: string;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "DisconnectReceiver".
 */
export interface DisconnectReceiver {
  v: 1;
  type: 'disconnect_receiver';
}
/**
 * Opt in to binary channels. Both default off: no bytes the viewer does not want.
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Subscribe".
 */
export interface Subscribe {
  v: 1;
  type: 'subscribe';
  audio: boolean;
  waterfall: boolean;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "Ping".
 */
export interface Ping {
  v: 1;
  type: 'ping';
}
/**
 * A recorded net with its traffic (GET /api/nets/{id}).
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "NetLog".
 */
export interface NetLog {
  summary: NetSummary;
  decodes: Decode[];
  stations: Station[];
  waterfall_seconds: number;
  waterfall_offset_lo_hz: number;
  waterfall_offset_hi_hz: number;
}
/**
 * One recorded GhostNet window (GET /api/nets).
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "NetSummary".
 */
export interface NetSummary {
  id: string;
  window_id: string;
  label: string;
  kind: 'net' | 'bridge';
  band: string;
  dial_hz: number;
  scheduled_start: string;
  scheduled_end: string;
  started: string;
  ended: string | null;
  receiver: string | null;
  receiver_reason: string;
  decode_count: number;
  station_count: number;
  has_audio: boolean;
  has_waterfall: boolean;
  flash_count: number;
  operator_override: boolean;
}
/**
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "ReceiverDirectory".
 */
export interface ReceiverDirectory {
  fetched_utc: string | null;
  stale: boolean;
  source: string;
  receivers: ReceiverListing[];
}
/**
 * One public receiver from the directory (GET /api/receivers).
 *
 * This interface was referenced by `GhostJs8Protocol`'s JSON-Schema
 * via the `definition` "ReceiverListing".
 */
export interface ReceiverListing {
  id: string;
  name: string;
  host: string;
  port: number;
  tls: boolean;
  location: string;
  grid: string | null;
  lat: number | null;
  lon: number | null;
  users: number;
  users_max: number;
  min_hz: number;
  max_hz: number;
  antenna: string;
  snr_db: number | null;
}
