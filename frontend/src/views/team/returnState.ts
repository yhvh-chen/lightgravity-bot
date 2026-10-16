/**
 * Cross-view return position for Team → Resources links (LG-015).
 *
 * This is a UI preference only (sessionStorage), never business state: the
 * authoritative Task/Run/Member data still comes from the backend.  It lets the
 * Resources detail offer "Back to Team" and restore the member that was open,
 * matching docs/05 §6.2 ("return to the original member").
 */
const KEY = 'lg015.team-return'

export interface TeamReturn {
  itemRef: string
}

export function rememberTeamReturn(itemRef: string): void {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return
    window.sessionStorage.setItem(KEY, JSON.stringify({ itemRef }))
  } catch {
    /* best effort: navigation still works without the remembered position */
  }
}

export function readTeamReturn(): TeamReturn | null {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return null
    const raw = window.sessionStorage.getItem(KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && typeof (parsed as TeamReturn).itemRef === 'string') {
      return parsed as TeamReturn
    }
    return null
  } catch {
    return null
  }
}

export function clearTeamReturn(): void {
  try {
    if (typeof window === 'undefined' || !window.sessionStorage) return
    window.sessionStorage.removeItem(KEY)
  } catch {
    /* ignore */
  }
}
