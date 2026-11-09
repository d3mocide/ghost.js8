<script lang="ts">
  // The operator gate's only UI. Viewers never see tuning / receiver / autopilot controls;
  // this is how an operator unlocks them. The bridge enforces it: hiding is only courtesy.
  import { useApp } from '../../lib/state/context';
  import { operatorLogin, operatorLogout } from '../../lib/operator';

  const app = useApp();
  let open = $state(false);
  let password = $state('');
  let busy = $state(false);
  let error = $state<string | null>(null);
  let field: HTMLInputElement | undefined = $state();

  $effect(() => {
    if (open) queueMicrotask(() => field?.focus());
  });

  async function submit(ev: SubmitEvent): Promise<void> {
    ev.preventDefault();
    if (busy || password === '') return;
    busy = true;
    error = null;
    const res = await operatorLogin(password);
    busy = false;
    password = '';
    if (res.ok) {
      open = false;
      app.reconnect();
    } else {
      error = res.message;
    }
  }

  async function signOut(): Promise<void> {
    await operatorLogout();
    app.reconnect();
  }
</script>

<svelte:window
  onkeydown={(e: KeyboardEvent) => {
    if (open && e.key === 'Escape') open = false;
  }}
/>

{#if app.operator && app.operatorAvailable}
  <button
    type="button"
    class="chip on"
    data-testid="operator-signout"
    title="Operator mode: you can tune and choose receivers. Click to sign out."
    onclick={() => {
      void signOut();
    }}
  >
    <span aria-hidden="true">●</span> Operator <span class="out">sign out</span>
  </button>
{:else if app.operatorAvailable}
  <div class="wrap">
    <button
      type="button"
      class="chip"
      aria-expanded={open}
      aria-controls="operator-login"
      data-testid="operator-toggle"
      title="Operator login: needed to tune or change the receiver"
      onclick={() => (open = !open)}
    >
      <span aria-hidden="true">⌁</span> Operator
    </button>
    {#if open}
      <form id="operator-login" class="pop" aria-label="Operator login" onsubmit={submit}>
        <label>
          <span class="sr-only">Operator password</span>
          <input
            bind:this={field}
            bind:value={password}
            type="password"
            autocomplete="current-password"
            placeholder="Operator password"
            maxlength="256"
            data-testid="operator-password"
          />
        </label>
        <button type="submit" class="go" disabled={busy || password === ''}>
          {busy ? '…' : 'Unlock'}
        </button>
        {#if error}<p class="err" role="alert">{error}</p>{/if}
      </form>
    {/if}
  </div>
{/if}

<style>
  .wrap {
    position: relative;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 28px;
    padding: 0 10px;
    border: 1px solid var(--g-border);
    border-radius: var(--g-radius-pill);
    background: var(--g-glass-raised);
    color: var(--g-text-muted);
    font-size: var(--g-text-xs);
    cursor: pointer;
  }
  .chip:hover {
    border-color: var(--g-border-strong);
  }
  .chip.on {
    color: var(--g-signal);
    border-color: rgb(94 234 212 / 0.35);
  }
  .out {
    color: var(--g-text-dim);
  }
  .pop {
    position: absolute;
    right: 0;
    top: calc(100% + 8px);
    z-index: 60;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    width: min(20rem, 86vw);
    padding: var(--g-space-3);
    border: 1px solid var(--g-border-strong);
    border-radius: var(--g-radius-m, 10px);
    background: rgb(8 10 18 / 0.96);
    backdrop-filter: blur(20px);
  }
  input {
    flex: 1 1 10rem;
    min-width: 0;
    min-height: 32px;
    padding: 0 10px;
    border: 1px solid var(--g-border);
    border-radius: 6px;
    background: var(--g-glass-raised);
    color: var(--g-text);
  }
  .go {
    min-height: 32px;
    padding: 0 14px;
    border: 1px solid rgb(94 234 212 / 0.4);
    border-radius: 6px;
    background: var(--g-signal-soft);
    color: var(--g-signal);
    cursor: pointer;
  }
  .go:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .err {
    flex-basis: 100%;
    margin: 0;
    color: var(--g-alert);
    font-size: var(--g-text-xs);
  }
</style>
