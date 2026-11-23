// RIGHTWARE JARVIS (UI-02): never offer the analytics/giveaway dialog (analytics are off by policy).
export function offerAnalyticsChoice(_args: unknown): (() => void) | undefined {
  return undefined;
}
