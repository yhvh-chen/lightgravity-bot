import type { ReactNode } from 'react'

export interface EmptyStateProps {
  title: string
  children?: ReactNode
  /** Marks this as a labeled layout mock rather than real data. */
  mock?: boolean
  compact?: boolean
}

/**
 * Empty/not-connected state (design.md §6). Every empty state must explain the
 * next step instead of showing a decorative illustration.
 */
export function EmptyState({ title, children, mock = false, compact = false }: EmptyStateProps) {
  return (
    <div
      className={`lg-state${compact ? ' lg-state--compact' : ''}`}
      role="status"
      data-mock={mock ? 'true' : undefined}
    >
      <p className="lg-state__title">{title}</p>
      {children ? <div className="lg-state__body">{children}</div> : null}
    </div>
  )
}
