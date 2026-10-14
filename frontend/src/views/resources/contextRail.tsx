import { useMemo } from 'react'

import {
  categoryById,
  categoryByKind,
  isResourceKind,
  RESOURCE_CATEGORIES,
} from '../../api/resources'
import { ContextList, type ContextItem, type ContextSection } from '../../components/ContextList'

export interface ContextRailProps {
  selectedId: string | null
  onSelect: (item: ContextItem) => void
}

function activeCategoryId(selectedId: string | null): string | null {
  if (!selectedId) return null
  if (selectedId.startsWith('resources:')) {
    const kind = selectedId.split(':')[1]
    if (kind && isResourceKind(kind)) return categoryByKind(kind)?.id ?? null
  }
  return categoryById(selectedId)?.id ?? null
}

/**
 * Data-driven Resources secondary rail (docs/05 §6.1).
 *
 * Exactly the seven frozen categories are entries; selecting one keeps the
 * Task scope and shows the real `/resources/{kind}` list.  A resource detail
 * (`resources:<kind>:<id>`) highlights its owning category.
 */
export function ResourcesContextRail({ selectedId, onSelect }: ContextRailProps) {
  const selected = useMemo(() => activeCategoryId(selectedId), [selectedId])
  const sections: ContextSection[] = [
    {
      id: 'resources-categories',
      title: 'Categories',
      items: RESOURCE_CATEGORIES.map((category) => ({
        id: category.id,
        label: category.label,
      })),
      empty: 'No categories.',
    },
  ]
  return (
    <ContextList
      sections={sections}
      selectedId={selected}
      onSelect={onSelect}
      ariaLabel="Resource categories"
    />
  )
}
