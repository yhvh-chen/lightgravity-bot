/**
 * Inline SVG icons (LG-011).
 *
 * design.md forbids pulling in a full icon library at shell stage, so the few
 * navigation/status glyphs are defined here as stroke SVGs. Icons are
 * decorative: every button carries its own accessible name.
 */
import type { SVGProps } from 'react'

export type IconName =
  | 'chat'
  | 'board'
  | 'files'
  | 'team'
  | 'resources'
  | 'settings'
  | 'panel-left'
  | 'panel-right'
  | 'menu'
  | 'bell'
  | 'close'
  | 'send'
  | 'check'
  | 'alert'
  | 'info'

const PATHS: Record<IconName, string> = {
  chat: 'M4 5h16v10H8l-4 4V5z',
  board: 'M4 4h5v16H4zM10 4h4v9h-4zM15 4h5v13h-5z',
  files: 'M4 5a1 1 0 0 1 1-1h5l2 2h7a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z',
  team: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20a6 6 0 0 1 12 0M17 11a3 3 0 1 0 0-6M16 20a5 5 0 0 1 5-5',
  resources: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9',
  settings:
    'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-2.7 1.1 2 2 0 1 1-4 0 1.6 1.6 0 0 0-2.7-1.1l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.6 1.6 0 0 0 4.6 15a2 2 0 1 1 0-4 1.6 1.6 0 0 0 1.1-2.7l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.6 1.6 0 0 0 12 4.6a2 2 0 1 1 4 0 1.6 1.6 0 0 0 2.7 1.1l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1A1.6 1.6 0 0 0 19.4 11a2 2 0 1 1 0 4z',
  'panel-left': 'M4 4h16v16H4zM10 4v16',
  'panel-right': 'M4 4h16v16H4zM14 4v16',
  menu: 'M4 6h16M4 12h16M4 18h16',
  bell: 'M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6zM10 19a2 2 0 0 0 4 0',
  close: 'M6 6l12 12M18 6L6 18',
  send: 'M4 12l16-8-6 16-3-6z',
  check: 'M4 12l5 5L20 6',
  alert: 'M12 4l9 16H3zM12 10v4M12 17h.01',
  info: 'M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16zM12 11v5M12 8h.01',
}

interface IconProps extends SVGProps<SVGSVGElement> {
  name: IconName
  size?: number
}

export function Icon({ name, size = 18, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      <path d={PATHS[name]} />
    </svg>
  )
}
