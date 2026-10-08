<script lang="ts">
  // The mark: a line-art sheet ghost in military-stencil style (bridges cut
  // into the outline), a radio-wave hem, and angled slit eyes.
  let { size = 28, wordmark = true }: { size?: number; wordmark?: boolean } = $props();
</script>

<span class="logo">
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
    <defs>
      <linearGradient id="ghostjs8-logo-grad" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="var(--g-accent-a)" />
        <stop offset="1" stop-color="var(--g-accent-b)" />
      </linearGradient>
      <mask id="ghostjs8-logo-stencil" maskUnits="userSpaceOnUse">
        <rect width="64" height="64" fill="#fff" />
        <!-- stencil bridges -->
        <rect x="30.4" y="10" width="3.2" height="7" />
        <rect x="11" y="37" width="9" height="2.6" />
        <rect x="44" y="37" width="9" height="2.6" />
      </mask>
    </defs>
    <path
      d="M16 50V30a16 16 0 0 1 32 0v20q-4 6-8 0t-8 0t-8 0t-8 0"
      fill="rgb(167 139 250 / 0.1)"
      stroke="url(#ghostjs8-logo-grad)"
      stroke-width="3.4"
      stroke-linejoin="round"
      mask="url(#ghostjs8-logo-stencil)"
    />
    <path class="eye" d="M22 29.5l8 2.4v3.4l-8-2.4z" />
    <path class="eye" d="M42 29.5l-8 2.4v3.4l8-2.4z" />
  </svg>
  {#if wordmark}
    <span class="word"
      >ghost<span class="dot">.</span>js8<span class="cursor" aria-hidden="true">_</span></span
    >
  {/if}
</span>

<style>
  .logo {
    display: inline-flex;
    align-items: center;
    gap: var(--g-space-2);
  }
  svg {
    flex: none;
    filter: drop-shadow(0 0 10px rgb(125 211 252 / 0.35));
  }
  .eye {
    fill: var(--g-signal);
    filter: drop-shadow(0 0 3px rgb(94 234 212 / 0.8));
  }
  .word {
    font-family: var(--g-font-display);
    font-size: 1.45rem;
    line-height: 1;
    letter-spacing: 0.02em;
    color: var(--g-text);
    text-shadow: 0 0 14px rgb(125 211 252 / 0.25);
  }
  .dot {
    color: var(--g-accent-a);
  }
  .cursor {
    margin-left: 1px;
    color: var(--g-signal);
    animation: blink 1.1s steps(2, start) infinite;
  }
  @keyframes blink {
    to {
      visibility: hidden;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .cursor {
      animation: none;
    }
  }
</style>
