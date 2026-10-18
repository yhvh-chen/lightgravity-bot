import { useId, type SVGProps } from 'react'

/**
 * Canonical LightGravity mark (LG-170).
 *
 * Geometry and brand colours are reused verbatim from the provided pitch
 * asset `pitch/lightgravity_bot_logo_showcase.html` (see `pitch/design.md`
 * §2–4): one closed compound path on a 240×240 viewBox, whose inner circle is
 * cut out by `fill-rule="evenodd"`, filled by the four-stop gravitational
 * spectrum. The pitch file itself is never modified or embedded; only this
 * small vector is shared by the login card and the signed-in shell.
 *
 * No external font, script, icon package or raster asset is involved, and the
 * mark inherits nothing from page state beyond its size. It is decorative by
 * default because every placement pairs it with visible brand text; the
 * gradient id is derived from `useId()` so multiple marks never collide.
 */
export interface LogoProps extends Omit<SVGProps<SVGSVGElement>, 'width' | 'height' | 'viewBox'> {
  /** Rendered edge length in px. */
  size?: number
}

export function Logo({ size = 24, className, ...rest }: LogoProps) {
  const gradientId = `lg-logo-gradient-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 240 240"
      xmlns="http://www.w3.org/2000/svg"
      {...rest}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#1BA1E3" />
          <stop offset="34%" stopColor="#5B72F2" />
          <stop offset="68%" stopColor="#8054F7" />
          <stop offset="100%" stopColor="#D96590" />
        </linearGradient>
      </defs>
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        fill={`url(#${gradientId})`}
        d="M 120 12
           C 123 68, 172 117, 228 120
           C 172 123, 123 172, 120 228
           C 117 172, 68 123, 12 120
           C 68 117, 117 68, 120 12 Z
           M 120 72
           A 48 48 0 1 0 120 168
           A 48 48 0 1 0 120 72 Z"
      />
    </svg>
  )
}
