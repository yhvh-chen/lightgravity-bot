import type { SourceView } from '../../api/sources'

/** Shared by material selectors; only the server can verify readable text bytes. */
export function isSourceContextSelectable(source: SourceView): boolean {
  return source.status !== 'archived' && source.status !== 'failed' && source.context_selectable === true
}

export function sourceContextUnavailableReason(source: SourceView): string {
  if (source.status === 'archived') return 'revoked — not selectable'
  if (source.status === 'failed') return 'failed — not selectable'
  if (source.context_selectable === undefined) return 'text availability unknown — refresh materials'
  return 'no readable text body — not selectable'
}
