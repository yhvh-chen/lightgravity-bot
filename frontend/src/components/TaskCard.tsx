import { MockBadge, StatusBadge, type StatusKind } from './StatusBadge'

export interface TaskCardProps {
  title: string
  phase: string
  statusLabel: string
  statusKind: StatusKind
  taskRef: string
  runRef?: string | null
  mock?: boolean
  selected?: boolean
  onOpen?: () => void
}

/**
 * Shared TaskCard (design.md §4). Phase drives the badge; a cancelled/failed
 * task is never shown as "running". Shell uses it for the labelled layout mock
 * until LG-013 wires real Board data.
 */
export function TaskCard({
  title,
  phase,
  statusLabel,
  statusKind,
  taskRef,
  runRef,
  mock = false,
  selected = false,
  onOpen,
}: TaskCardProps) {
  const className = `lg-card${selected ? ' is-selected' : ''}${
    onOpen ? ' lg-card--interactive' : ''
  }`
  const body = (
    <>
      <div className="lg-card__head">
        <h3 className="lg-card__title">{title}</h3>
        <span className="lg-card__meta">
          {mock ? <MockBadge /> : null}
          <StatusBadge kind={statusKind}>{statusLabel}</StatusBadge>
        </span>
      </div>
      <div className="lg-card__meta">
        <span className="lg-card__path">{taskRef}</span>
        <span>phase: {phase}</span>
        {runRef ? <span className="lg-card__path">{runRef}</span> : null}
      </div>
    </>
  )

  if (onOpen) {
    return (
      <button type="button" className={className} aria-pressed={selected} onClick={onOpen}>
        {body}
      </button>
    )
  }
  return <article className={className}>{body}</article>
}
