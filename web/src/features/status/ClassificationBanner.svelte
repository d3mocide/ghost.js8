<script lang="ts">
  import { useApp } from '../../lib/state/context';
  import { utcTime } from '../../lib/format';

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

<div class="banner" role="banner">
  <span class="cls">RECEIVE ONLY // PASSIVE LISTENING POST</span>
  <span class="mid" aria-hidden="true">GHOST.JS8</span>
  <span class="right">
    <span class="link {link}" data-testid="link-state">
      <span aria-hidden="true">{link === 'open' ? '●' : '○'}</span>
      {linkText}
    </span>
    <time class="utc mono" datetime={new Date(app.now).toISOString()} aria-label="UTC time">
      {utcTime(new Date(app.now))}Z
    </time>
  </span>
</div>

<style>
  .banner {
    position: sticky;
    top: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    gap: var(--g-space-3);
    height: var(--g-banner-h);
    padding: 0 var(--g-gutter);
    background: linear-gradient(
      90deg,
      rgb(61 255 154 / 0.1),
      rgb(92 225 255 / 0.06) 50%,
      rgb(61 255 154 / 0.1)
    );
    border-bottom: 1px solid rgb(61 255 154 / 0.35);
    font-family: var(--g-font-mono);
    font-size: var(--g-text-xs);
    letter-spacing: var(--g-tracking-caps);
    white-space: nowrap;
    backdrop-filter: blur(8px);
  }
  .cls {
    color: var(--g-signal);
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .mid {
    flex: 1;
    text-align: center;
    color: var(--g-text-dim);
  }
  .right {
    display: flex;
    gap: var(--g-space-3);
    align-items: center;
  }
  .link.open {
    color: var(--g-signal);
  }
  .link.connecting,
  .link.reconnecting {
    color: var(--g-warn);
  }
  .link.closed {
    color: var(--g-alert);
  }
  .utc {
    color: var(--g-text);
  }
  @media (max-width: 720px) {
    .mid,
    .cls {
      display: none;
    }
    .right {
      margin-left: auto;
    }
  }
</style>
