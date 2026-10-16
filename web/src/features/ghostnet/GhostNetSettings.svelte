<script lang="ts">
  import { useApp } from '../../lib/state/context';
  import {
    receiverLabel,
    sameReceiver,
    settingsMessage,
    windowWhen,
    type SettingsChange,
  } from '../../lib/ghostnet';
  import { formatMHz } from '../../lib/format';
  import type { GhostNet, GhostNetWindowSetting } from '../../lib/protocol/generated';

  const { g }: { g: GhostNet } = $props();
  const app = useApp();

  // The receiver the bridge is listening to right now, if it is delivering audio.
  const current = $derived(
    app.state.session?.state === 'connected' ? (app.state.session.receiver ?? null) : null,
  );
  const SETTINGS_ERRORS = ['invalid_settings', 'invalid_receiver', 'unavailable', 'rate_limited'];
  const problem = $derived(
    app.state.lastError && SETTINGS_ERRORS.includes(app.state.lastError.code)
      ? app.state.lastError.message
      : null,
  );
  const nets = $derived(g.windows.filter((w) => w.kind === 'net'));
  const bridges = $derived(g.windows.filter((w) => w.kind === 'bridge'));
  const groups = $derived<readonly (readonly [string, readonly GhostNetWindowSetting[]])[]>([
    ['Nets', nets],
    ['Data bridges', bridges],
  ]);
  const followed = $derived(g.windows.filter((w) => w.enabled).length);

  function change(c: SettingsChange): void {
    app.dispatch({ type: 'clear-error' });
    app.send(settingsMessage(c));
  }

  // The bridge is the source of truth: put the box back and let its broadcast flip it.
  function toggle(ev: Event, current: boolean, c: SettingsChange): void {
    (ev.currentTarget as HTMLInputElement).checked = current;
    change(c);
  }

  function pinCurrent(w: GhostNetWindowSetting): void {
    if (!current) return;
    change({
      windows: {
        [w.id]: {
          receiver: {
            host: current.host,
            port: current.port,
            name: current.name,
            tls: current.tls,
          },
        },
      },
    });
  }
</script>

<details class="settings" data-testid="gn-settings">
  <summary>
    Autopilot settings
    <span class="count mono">{followed}/{g.windows.length} nets followed</span>
  </summary>

  <div class="switches">
    <label>
      <input
        type="checkbox"
        data-testid="gn-autopilot"
        checked={g.autopilot_enabled}
        onchange={(ev) => {
          toggle(ev, g.autopilot_enabled, { autopilotEnabled: !g.autopilot_enabled });
        }}
      />
      <span>Autopilot</span>
      <small>on: follows the plan below; off: leaves the receiver to you</small>
    </label>
    <label>
      <input
        type="checkbox"
        data-testid="gn-park"
        checked={g.park}
        disabled={!g.autopilot_enabled}
        onchange={(ev) => {
          toggle(ev, g.park, { park: !g.park });
        }}
      />
      <span>Watch 7.107 between nets</span>
      <small>keep decoding (not recorded)</small>
    </label>
    <label>
      <input
        type="checkbox"
        data-testid="gn-record-audio"
        checked={g.record_audio}
        disabled={!g.autopilot_enabled}
        onchange={(ev) => {
          toggle(ev, g.record_audio, { recordAudio: !g.record_audio });
        }}
      />
      <span>Record audio</span>
      <small>takes effect from the next net</small>
    </label>
  </div>

  {#if problem}<p class="problem" role="alert" data-testid="gn-settings-error">{problem}</p>{/if}

  {#each groups as [title, windows] (title)}
    {#if windows.length > 0}
      <h4 class="caps">{title}</h4>
      <ul class="plan" aria-label={title}>
        {#each windows as w (w.id)}
          <li class:off={!w.enabled || !g.autopilot_enabled} data-testid={`gn-window-${w.id}`}>
            <label class="follow">
              <input
                type="checkbox"
                data-testid={`gn-follow-${w.id}`}
                checked={w.enabled}
                disabled={!g.autopilot_enabled}
                onchange={(ev) => {
                  toggle(ev, w.enabled, { windows: { [w.id]: { enabled: !w.enabled } } });
                }}
              />
              <span class="name">{w.label}</span>
            </label>
            <div class="when mono">
              {windowWhen(w)} · {w.band} · {formatMHz(w.dial_hz)} MHz
            </div>
            <div class="rx">
              {#if w.receiver}
                <span class="muted">Prefers</span>
                <strong data-testid={`gn-pref-${w.id}`}>{receiverLabel(w.receiver)}</strong>
                <button
                  class="btn ghost small"
                  type="button"
                  aria-label={`Back to automatic receiver for ${w.label}`}
                  onclick={() => {
                    change({ windows: { [w.id]: { clearReceiver: true } } });
                  }}>Auto</button
                >
              {:else}
                <span class="muted">Receiver: best available at the time</span>
              {/if}
              {#if current && !sameReceiver(current, w.receiver)}
                <button
                  class="btn ghost small"
                  type="button"
                  data-testid={`gn-pin-${w.id}`}
                  title={`Prefer ${receiverLabel(current)} for ${w.label}. If it fails, the best other receiver is used.`}
                  onclick={() => {
                    pinCurrent(w);
                  }}>Use {receiverLabel(current)}</button
                >
              {/if}
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  {/each}

  <p class="foot muted">
    A preferred receiver is tried first for its net; if it fails, the best other one is used for the
    rest of that net.
  </p>
</details>

<style>
  .settings {
    margin-top: var(--g-space-3);
    font-size: var(--g-text-s);
  }
  summary {
    display: flex;
    justify-content: space-between;
    gap: var(--g-space-2);
    align-items: baseline;
    cursor: pointer;
    color: var(--g-chrome);
    font-weight: 600;
  }
  .count {
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
    font-weight: 400;
  }
  .switches {
    display: grid;
    gap: var(--g-space-2);
    margin-top: var(--g-space-3);
  }
  .switches label {
    display: grid;
    grid-template-columns: auto 1fr;
    column-gap: var(--g-space-2);
    align-items: center;
  }
  .switches small {
    grid-column: 2;
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
  }
  h4 {
    margin: var(--g-space-4) 0 var(--g-space-2);
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }
  .plan {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: var(--g-space-2);
  }
  .plan li {
    display: grid;
    gap: 2px;
    padding: var(--g-space-2) var(--g-space-3);
    border: 1px solid var(--g-hairline);
    border-radius: var(--g-radius-m);
    background: var(--g-glass-raised);
  }
  .plan li.off {
    opacity: 0.55;
  }
  .follow {
    display: flex;
    align-items: center;
    gap: var(--g-space-2);
    min-width: 0;
  }
  .name {
    font-weight: 600;
    min-width: 0;
  }
  .when {
    font-size: var(--g-text-xs);
    color: var(--g-text-muted);
    padding-left: calc(13px + var(--g-space-2));
  }
  .rx {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--g-space-2);
    padding-left: calc(13px + var(--g-space-2));
    font-size: var(--g-text-xs);
  }
  .muted {
    color: var(--g-text-muted);
  }
  .small {
    padding: 1px 8px;
    font-size: var(--g-text-xs);
    min-height: 0;
  }
  .problem {
    margin: var(--g-space-3) 0 0;
    color: var(--g-warn);
    font-size: var(--g-text-xs);
  }
  .foot {
    margin: var(--g-space-3) 0 0;
    font-size: var(--g-text-xs);
  }
</style>
