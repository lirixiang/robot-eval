// Shared status chip and retry badge — single source of truth for status → CSS class mapping.
import type { Job } from '../types'

export const STATUS_CHIP_CLASS: Record<string, string> = {
  running:       'chip-run',
  done:          'chip-done',
  failed:        'chip-fail',
  failed_final:  'chip-fail',
  pending:       'chip-pend',
  cancelled:     'chip',
  retry_pending: 'chip-pend',
}

export function StatusChip({ status }: { status: Job['status'] }) {
  return <span className={`chip ${STATUS_CHIP_CLASS[status] ?? 'chip'}`}>{status}</span>
}

export function RetryBadge({ retryCount, maxRetries }: { retryCount?: number | null; maxRetries?: number | null }) {
  if (!retryCount) return null
  return (
    <span className="px-1.5 py-0.5 rounded text-[10px] bg-red-900/40 text-red-400 border border-red-800/40">
      重试 {retryCount}/{maxRetries ?? 3}
    </span>
  )
}
