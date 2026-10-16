import type { ReactNode } from 'react'

import { MockBadge } from './StatusBadge'

export interface DetailHeaderProps {
  title: string
  /** Badges (status/phase/mock) rendered next to the title. */
  badges?: ReactNode
  meta?: ReadonlyArray<{ label: string; value: string }>
  mock?: boolean
  actions?: ReactNode
}

/**
 * Shared DetailHeader (design.md §4, §5). Stable order: title/status, key
 * fields, then actions. Used by all detail views so headers stay consistent.
 */
export function DetailHeader({ title, badges, meta, mock = false, actions }: DetailHeaderProps) {
  return (
    <div className="lg-detail-header">
      <div className="lg-detail-header__top">
        <h2 className="lg-detail-header__title">{title}</h2>
        {mock ? <MockBadge label="mock item" /> : null}
        {badges}
        {actions ? <span className="lg-topbar__spacer" /> : null}
        {actions}
      </div>
      {meta && meta.length > 0 ? (
        <div className="lg-detail-header__meta">
          {meta.map((entry) => (
            <span key={entry.label}>
              {entry.label}: <span className="lg-card__path">{entry.value}</span>
            </span>
          ))}
        </div>
      ) : null}
    </div>
  )
}
