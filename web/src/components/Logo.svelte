<script lang="ts">
  // The mark: a ghost whose hem is a signal trace, eyes as redaction bars.
  let { size = 28, wordmark = true }: { size?: number; wordmark?: boolean } = $props();
</script>

<span class="logo">
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
    <path
      d="M14 50V29a18 18 0 0 1 36 0v21l-4.5-4-4.5 4-4.5-6-4.5 6-4.5-6-4.5 6z"
      fill="rgb(92 225 255 / 0.08)"
      stroke="var(--g-chrome)"
      stroke-width="3.2"
      stroke-linejoin="round"
    />
    <rect class="eye" x="22" y="27" width="8" height="4" rx="1" />
    <rect class="eye" x="34" y="27" width="8" height="4" rx="1" />
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
  .eye {
    fill: var(--g-signal);
    filter: drop-shadow(0 0 3px rgb(61 255 154 / 0.7));
  }
  .word {
    font-family: var(--g-font-mono);
    font-weight: 600;
    font-size: var(--g-text-l);
    letter-spacing: 0.02em;
    color: var(--g-text);
  }
  .dot {
    color: var(--g-signal);
  }
</style>
