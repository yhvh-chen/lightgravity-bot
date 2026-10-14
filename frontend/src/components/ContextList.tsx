import type { ReactNode } from 'react'

import { EmptyState } from './EmptyState'
import { MockBadge, StatusBadge, type StatusKind } from './StatusBadge'

export interface ContextItem {
  id: string
  label: string
  meta?: string
  status?: { kind: StatusKind; label: string }
  /** True when this item comes from the labelled layout mock. */
  mock?: boolean
  /** When set, selecting the item also makes it the active Task scope. */
  taskRef?: string
}

export interface ContextSection {
  id: string
  title: string
  items: readonly ContextItem[]
  /** Copy shown when the section has no items (never a bare blank area). */
  empty?: string
}

export interface ContextListProps {
  sections: readonly ContextSection[]
  selectedId?: string | null
  onSelect: (item: ContextItem, section: ContextSection) => void
  ariaLabel: string
  header?: ReactNode
}

/**
 * Shared context rail content (design.md §4 ContextList). Selection is kept in
 * shell state so switching views preserves it (LG-011 acceptance).
 */
export function ContextList({ sections, selectedId, onSelect, ariaLabel, header }: ContextListProps) {
  return (
    <div className="lg-context__body">
      {header}
      <div role="group" aria-label={ariaLabel}>
        {sections.map((section) => (
          <section className="lg-section" key={section.id} aria-labelledby={`ctx-${section.id}`}>
            <h3 className="lg-section__title" id={`ctx-${section.id}`}>
              {section.title}
            </h3>
            {section.items.length === 0 ? (
              <EmptyState title={section.empty ?? 'Nothing here yet'} compact />
            ) : (
              <ul className="lg-context-list">
                {section.items.map((item) => {
                  const selected = item.id === selectedId
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={`lg-context-item${selected ? ' is-selected' : ''}`}
                        aria-pressed={selected}
                        onClick={() => onSelect(item, section)}
                      >
                        <span className="lg-context-item__body">
                          <span className="lg-context-item__label">{item.label}</span>
                          {item.meta ? (
                            <span className="lg-context-item__meta">{item.meta}</span>
                          ) : null}
                        </span>
                        {item.status ? (
                          <StatusBadge kind={item.status.kind}>{item.status.label}</StatusBadge>
                        ) : null}
                        {item.mock ? <MockBadge /> : null}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        ))}
      </div>
    </div>
  )
}
