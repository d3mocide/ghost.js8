<script lang="ts">
  // The mark: a ghost whose hem is a signal trace, eyes as redaction bars.
  let { size = 28, wordmark = true }: { size?: number; wordmark?: boolean } = $props();
</script>

<span class="logo">
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
    <defs>
      <linearGradient id="ghostjs8-logo-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="var(--g-accent-a)" />
        <stop offset="1" stop-color="var(--g-accent-b)" />
      </linearGradient>
    </defs>
    <path
      d="M14 50V29a18 18 0 0 1 36 0v21l-4.5-4-4.5 4-4.5-6-4.5 6-4.5-6-4.5 6z"
      fill="rgb(167 139 250 / 0.12)"
      stroke="url(#ghostjs8-logo-grad)"
      stroke-width="3.4"
      stroke-linejoin="round"
    />
    <rect class="eye" x="22" y="27" width="8" height="4" rx="2" />
    <rect class="eye" x="34" y="27" width="8" height="4" rx="2" />
  </svg>
  {#if wordmark}
    <span class="word">ghost<span class="dot">.</span>js8</span>
  {/if}
</span>

<style>
  .logo {
    display: inline-flex;
    align-items: center;
    gap: var(--g-space-2);
  }
  svg {
    filter: drop-shadow(0 0 10px rgb(125 211 252 / 0.35));
  }
  .eye {
    fill: var(--g-signal);
    filter: drop-shadow(0 0 3px rgb(94 234 212 / 0.8));
  }
  .word {
    font-family: var(--g-font-ui);
    font-weight: 600;
    font-size: var(--g-text-l);
    letter-spacing: -0.01em;
    color: var(--g-text);
  }
  .dot {
    background: var(--g-accent);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
</style>
