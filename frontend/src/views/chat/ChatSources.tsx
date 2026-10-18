/**
 * Chat reply Sources block (LG-044; docs/10 §4, §7, §9).
 *
 * Renders the **provided context source bindings** the backend resolved for a
 * reply. It is deliberately labelled `Sources` (never `Verified citations`) and
 * repeats the backend's own note that the provided context is NOT span-verified
 * — this component must never claim a model actually used or cited a source.
 *
 * Each binding shows the real `source_id`/`source_version`/`content_hash`, the
 * layer (`formal`/`machine`), and — when the backend truncated the body — the
 * explicit truncation feedback (`truncated`, kept vs original char counts).
 *
 * A binding can be opened back in Tasks (the authoritative material surface);
 * the backlink is an in-app route with the real `source_id`, not a fabricated
 * local file URL.
 */

import type { ResolvedSourceBinding, ResolvedSourceBindingsData } from '../../api/chat'
import { StatusBadge } from '../../components/StatusBadge'

export interface ChatSourcesProps {
  data: ResolvedSourceBindingsData | null | undefined
  /** Open one source back in Tasks at this id (real in-app route). */
  onOpen: (sourceId: string) => void
}

export function ChatSources({ data, onOpen }: ChatSourcesProps) {
  const bindings = data?.resolved_source_bindings ?? []
  if (data?.unavailable === true || bindings.length === 0) return null
  const truncated = data?.context_truncated === true || bindings.some((b) => b.truncated)
  const note =
    data?.provided_context_note ??
    'Sources are provided as context; citations are NOT span-verified.'

  return (
    <section className="lg-chat-sources" aria-label="Sources">
      <div className="lg-chat-sources__header">
        <span className="lg-chat-sources__title">Sources</span>
        <StatusBadge kind="neutral">provided context</StatusBadge>
        {truncated ? <StatusBadge kind="warning">truncated</StatusBadge> : null}
      </div>
      <ul className="lg-chat-sources__list">
        {bindings.map((binding) => (
          <SourceBindingRow
            key={`${binding.source_id}-${binding.source_version}`}
            binding={binding}
            onOpen={onOpen}
          />
        ))}
      </ul>
      <p className="lg-chat-sources__note">{note}</p>
    </section>
  )
}

function SourceBindingRow({
  binding,
  onOpen,
}: {
  binding: ResolvedSourceBinding
  onOpen: (sourceId: string) => void
}) {
  return (
    <li className="lg-chat-sources__item">
      <div className="lg-chat-sources__item-head">
        <span className="lg-materials__name" title={binding.source_id}>
          {binding.source_id}
        </span>
        <StatusBadge kind="neutral">v{binding.source_version}</StatusBadge>
        <StatusBadge kind="neutral">{binding.layer}</StatusBadge>
        {binding.truncated ? <StatusBadge kind="warning">truncated</StatusBadge> : null}
      </div>
      <div className="lg-chat-sources__item-meta">
        {binding.content_hash ? (
          <span className="lg-card__path" title={binding.content_hash}>
            #{binding.content_hash.slice(0, 12)}
          </span>
        ) : null}
        <span className="lg-materials__flag">locator: {binding.locator}</span>
        <span className="lg-materials__flag">{binding.char_count} chars</span>
        <button type="button" className="lg-link-button" onClick={() => onOpen(binding.source_id)}>
          Open in Tasks
        </button>
      </div>
      {binding.truncated && binding.truncation ? (
        <p className="lg-chat-sources__truncation">
          Truncated: kept {binding.truncation.kept_char_count} of{' '}
          {binding.truncation.original_char_count} chars (max total{' '}
          {binding.truncation.max_total}; reason: {binding.truncation.reason}).
        </p>
      ) : null}
    </li>
  )
}
