import { useEffect, useState } from 'react'

/**
 * Small matchMedia hook (LG-011), used to switch the shell between
 * multi-column desktop and compact/mobile drawer layouts (design.md §7).
 * Returns false when matchMedia is unavailable (e.g. jsdom without a mock).
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState<boolean>(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return false
    }
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return
    }
    const list = window.matchMedia(query)
    setMatches(list.matches)
    const handler = (event: MediaQueryListEvent) => setMatches(event.matches)
    list.addEventListener('change', handler)
    return () => list.removeEventListener('change', handler)
  }, [query])

  return matches
}

export const COMPACT_QUERY = '(max-width: 1023px)'
export const MOBILE_QUERY = '(max-width: 699px)'

export function useIsCompact(): boolean {
  return useMediaQuery(COMPACT_QUERY)
}

export function useIsMobile(): boolean {
  return useMediaQuery(MOBILE_QUERY)
}
