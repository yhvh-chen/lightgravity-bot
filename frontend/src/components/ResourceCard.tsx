import { MockBadge, StatusBadge, type StatusKind } from './StatusBadge'

export interface ResourceCardProps {
  title: string
  kind: string
  path?: string
  /** Declaration vs actual availability stay separate (design.md §5). */
  availability?: { kind: StatusKind; label: string }
  mock?: boolean
  onOpen?: () => void
}

/** Shared ResourceCard for Team/Resources lists (design.md §4). */
export function ResourceCard({
  title,
  kind,
  path,
  availability,
  mock = false,
  onOpen,
}: ResourceCardProps) {
  const className = `lg-card${onOpen ? ' lg-card--interactive' : ''}`
  const body = (
    <>
      <div className="lg-card__head">
        <h3 className="lg-card__title">{title}</h3>
        <span className="lg-card__meta">
          {mock ? <MockBadge /> : null}
          {availability ? (
            <StatusBadge
              kind={availability.kind}
              title={`${kind} availability (declared, not a live check)`}
            >
              {availability.label}
            </StatusBadge>
          ) : null}
        </span>
      </div>
      <div className="lg-card__meta">
        <span>kind: {kind}</span>
      </div>
      {path ? <span className="lg-card__path">{path}</span> : null}
    </>
  )

  if (onOpen) {
    return (
      <button type="button" className={className} onClick={onOpen}>
        {body}
      </button>
    )
  }
  return <article className={className}>{body}</article>
}
