import type { ResourceDiagnostic } from '../../api/resources'
import { StatusBadge } from '../../components/StatusBadge'

export interface DiagnosticsProps {
  diagnostics: ReadonlyArray<ResourceDiagnostic>
}

/**
 * Parsed-frontmatter diagnostics (design.md §5 Resources).  Invalid resources
 * surface the real code/message/location instead of hiding behind a generic
 * "unavailable" state.
 */
export function Diagnostics({ diagnostics }: DiagnosticsProps) {
  if (diagnostics.length === 0) return null
  return (
    <section className="lg-resource-block" aria-label="Diagnostics">
      <h4 className="lg-section__title">Diagnostics</h4>
      <ul className="lg-diagnostics">
        {diagnostics.map((item, index) => (
          <li key={`${item.code}-${index}`}>
            <StatusBadge kind={item.level === 'warning' ? 'warning' : 'error'}>
              {item.code}
            </StatusBadge>{' '}
            {item.message}
            {item.location ? <span className="lg-card__path"> {item.location}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  )
}
