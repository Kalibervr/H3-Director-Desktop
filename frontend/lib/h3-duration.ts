/** Local UI formatting only; persisted timing remains backend authoritative. */
export function formatH3Duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) return 'Not recorded'
  const total = Math.round(seconds)
  if (total < 60) return `${total} sec`
  const minutes = Math.floor(total / 60)
  const remainder = total % 60
  if (minutes < 60) return `${minutes}m ${String(remainder).padStart(2, '0')}s`
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`
}
