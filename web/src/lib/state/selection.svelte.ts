// Which callsign's history is open in the Heard stations card. Shared so any callsign in the UI can open it.

class Selection {
  call = $state<string | null>(null);

  open(callsign: string): void {
    this.call = callsign.trim().toUpperCase();
  }

  close(): void {
    this.call = null;
  }
}

export const selection = new Selection();
