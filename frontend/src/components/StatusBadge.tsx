import type { ReactNode } from 'react'

export type StatusKind = 'neutral' | 'accent' | 'success' | 'warning' | 'error'

export interface StatusBadgeProps {
  kind?: StatusKind
  children: ReactNode
  /** Optional accessible clarification, e.g. the full phase name. */
  title?: string
}

/**
 * Shared status pill (design.md §4). Status is never conveyed by color alone:
 * the label text always carries the meaning.
 */
export function StatusBadge({ kind = 'neutral', children, title }: StatusBadgeProps) {
  return (
    <span className={`lg-status-badge lg-status-badge--${kind}`} title={title}>
      {children}
    </span>
  )
}

/** Marks any surface that renders layout-mock data. */
export function MockBadge({ label = 'mock' }: { label?: string }) {
  return (
    <span className="lg-mock-badge" title="Layout mock only — not backend data">
      {label}
    </span>
  )
}
