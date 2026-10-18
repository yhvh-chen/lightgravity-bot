/**
 * Inline SVG icons (LG-011; resource glyphs LG-102).
 *
 * design.md forbids pulling in a full icon library at shell stage, so the few
 * navigation/status glyphs are defined here as stroke SVGs. Icons are
 * decorative: every button carries its own accessible name.
 *
 * Most resource paths are adapted from Lucide (ISC licensed); the hook is a
 * small custom outline. All seven resource entries share one 24px/1.7-stroke
 * family instead of the old generic cube. No icon package is added to the build.
 */
import type { SVGProps } from 'react'

export type IconName =
  | 'chat'
  | 'board'
  | 'files'
  | 'link'
  | 'team'
  | 'resources'
  | 'connection'
  | 'session-profile'
  | 'hook'
  | 'mcp'
  | 'tool'
  | 'trigger'
  | 'skill'
  | 'settings'
  | 'panel-left'
  | 'panel-right'
  | 'menu'
  | 'bell'
  | 'history'
  | 'close'
  | 'send'
  | 'check'
  | 'alert'
  | 'info'

const PATHS: Record<IconName, string | readonly string[]> = {
  chat: 'M4 5h16v10H8l-4 4V5z',
  board: 'M4 4h5v16H4zM10 4h4v9h-4zM15 4h5v13h-5z',
  files: 'M4 5a1 1 0 0 1 1-1h5l2 2h7a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z',
  link: 'M10 14a4 4 0 0 1 0-6l1-1a4 4 0 0 1 6 6l-1 1M14 10a4 4 0 0 1 0 6l-1 1a4 4 0 0 1-6-6l1-1',
  team: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20a6 6 0 0 1 12 0M17 11a3 3 0 1 0 0-6M16 20a5 5 0 0 1 5-5',
  resources: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9',
  connection: [
    'M12 22v-5',
    'M15 8V2',
    'M17 8a1 1 0 0 1 1 1v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1z',
    'M9 8V2',
  ],
  'session-profile': [
    'M16 10h2M16 14h2',
    'M6.17 15a3 3 0 0 1 5.66 0',
    'M11 11a2 2 0 1 1-4 0 2 2 0 0 1 4 0z',
    'M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z',
  ],
  hook: [
    'M6 4h6',
    'M9 4v10a4.5 4.5 0 0 0 9 0v-2',
  ],
  mcp: [
    'M10 3h4v4h-4z',
    'M3 17h4v4H3z',
    'M17 17h4v4h-4z',
    'M5 17v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3M12 12V7',
  ],
  tool: 'M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z',
  trigger: 'M15.914 4a1.5 1.5 0 0 0-2.474-1.561l-9 9A1.5 1.5 0 0 0 5.5 14h4.002a.5.5 0 0 1 .471.666L8.086 20a1.5 1.5 0 0 0 2.475 1.56l9-9A1.5 1.5 0 0 0 18.5 10h-3.997a.5.5 0 0 1-.472-.667z',
  skill: [
    'M12 5v16',
    'M20.001 19A2 2 0 0 0 22 17V5a2 2 0 0 0-1.999-2L16 3.002A5 5 0 0 0 12 5a5 5 0 0 0-4-2H4a2 2 0 0 0-2 2v12a2 2 0 0 0 1.999 2H8a5 5 0 0 1 4 2 5 5 0 0 1 4-2z',
  ],
  settings: [
    'M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915',
    'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  ],
  'panel-left': 'M4 4h16v16H4zM10 4v16',
  'panel-right': 'M4 4h16v16H4zM14 4v16',
  menu: 'M4 6h16M4 12h16M4 18h16',
  bell: 'M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6zM10 19a2 2 0 0 0 4 0',
  history: [
    'M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8',
    'M3 3v5h5',
    'M12 7v5l4 2',
  ],
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
  const paths = PATHS[name]

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
      {(typeof paths === 'string' ? [paths] : paths).map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  )
}
