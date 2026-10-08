<script lang="ts">
  import Logo from '../../components/Logo.svelte';
  import { useApp } from '../../lib/state/context';
  import { utcTime } from '../../lib/format';
  import { backdrop } from '../../lib/backdrop/mode.svelte';

  const app = useApp();
  const link = $derived(app.state.link);
  const linkText = $derived(
    link === 'open'
      ? 'LINK ESTABLISHED'
      : link === 'closed'
        ? 'LINK CLOSED'
        : link === 'reconnecting'
          ? 'LINK LOST — REACQUIRING'
          : 'ACQUIRING LINK',
  );
</script>

<div class="topbar" role="banner">
  <div class="inner">
    <a class="brand" href="#/" aria-label="ghost.js8 home"><Logo size={30} /></a>
    <span class="tagline">JS8 listening post</span>
    <span class="spacer"></span>
    <button
      type="button"
      class="fx"
      aria-pressed={backdrop.mode === 'signal'}
      title={backdrop.mode === 'signal'
        ? 'Animated ASCII backdrop on: click for a still background'
        : 'Still background: click for the animated ASCII backdrop'}
      onclick={() => {
        backdrop.toggle();
      }}
    >
      <span class="glyph mono" aria-hidden="true"
        >{backdrop.mode === 'signal' ? '((·))' : '( · )'}</span
      >
      <span class="sr-only">Animated backdrop</span>
    </button>
    <span class="rx-only" title="ghost.js8 cannot transmit">
      <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true"
        ><path
          d="M12 3 4 6v6c0 4.4 3.4 8.3 8 9 4.6-.7 8-4.6 8-9V6z"
          fill="none"
          stroke="currentColor"
          stroke-width="2.2"
          stroke-linejoin="round"
        /></svg
      >
      Receive only
    </span>
    <span class="link {link}" data-testid="link-state">
      <span class="dot" aria-hidden="true"></span>
      <span class="label">{linkText}</span>
    </span>
    <time class="utc mono" datetime={new Date(app.now).toISOString()} aria-label="UTC time">
      {utcTime(new Date(app.now))}<span class="z">Z</span>
    </time>
  </div>
</div>

<style>
  .topbar {
    position: sticky;
    top: 0;
    z-index: 50;
    padding: var(--g-space-2) var(--g-gutter);
    background: linear-gradient(180deg, rgb(5 6 12 / 0.75), rgb(5 6 12 / 0.35));
    border-bottom: 1px solid var(--g-hairline);
    backdrop-filter: blur(18px) saturate(160%);
    -webkit-backdrop-filter: blur(18px) saturate(160%);
  }
  .inner {
    max-width: 1680px;
    margin: 0 auto;
    display: flex;
    align-items: center;
    gap: var(--g-space-3);
    min-height: 40px;
    white-space: nowrap;
  }
  .brand {
    color: inherit;
    text-decoration: none;
  }
  .tagline {
    padding-left: var(--g-space-3);
    border-left: 1px solid var(--g-border);
    color: var(--g-text-muted);
    font-size: var(--g-text-s);
  }
  .spacer {
    flex: 1;
  }
  .fx {
    display: inline-flex;
    align-items: center;
    min-height: 28px;
    padding: 0 10px;
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-pill);
    background: var(--g-glass-raised);
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
    cursor: pointer;
    transition:
      color var(--g-dur-fast) var(--g-ease),
      border-color var(--g-dur-fast) var(--g-ease);
  }
  .fx[aria-pressed='true'] {
    color: var(--g-signal);
    border-color: rgb(94 234 212 / 0.35);
  }
  .fx:hover {
    border-color: var(--g-border-strong);
  }
  .rx-only {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: var(--g-radius-pill);
    background: var(--g-signal-soft);
    color: var(--g-signal);
    font-size: var(--g-text-xs);
    font-weight: 600;
    letter-spacing: 0.04em;
  }
  .link {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-family: var(--g-font-mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    color: var(--g-text-muted);
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: currentColor;
  }
  .link.open .dot {
    color: var(--g-signal);
    box-shadow:
      0 0 0 3px rgb(94 234 212 / 0.18),
      0 0 10px var(--g-signal);
  }
  .link.connecting,
  .link.reconnecting {
    color: var(--g-warn);
  }
  .link.closed {
    color: var(--g-alert);
  }
  .utc {
    padding: 4px 10px;
    border-radius: var(--g-radius-s);
    background: var(--g-glass-raised);
    border: 1px solid var(--g-border);
    color: var(--g-text);
    font-size: var(--g-text-s);
  }
  .z {
    color: var(--g-text-dim);
    margin-left: 1px;
  }
  @media (max-width: 900px) {
    .tagline {
      display: none;
    }
  }
  @media (max-width: 720px) {
    .rx-only,
    .link .label {
      display: none;
    }
  }
</style>
