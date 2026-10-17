import type { StatusKind } from '../../components/StatusBadge'
import { StatusBadge } from '../../components/StatusBadge'
import type { ConnectionTestResult, TestLayer } from '../../api/settings'

function layerKind(status: string): StatusKind {
  switch (status) {
    case 'passed':
      return 'success'
    case 'declared':
      return 'accent'
    case 'failed':
      return 'error'
    default:
      return 'neutral'
  }
}

function overallKind(overall: string): StatusKind {
  switch (overall) {
    case 'verified':
      return 'success'
    case 'partial':
      return 'warning'
    case 'failed':
      return 'error'
    default:
      return 'neutral'
  }
}

export interface ConnectionTestPanelProps {
  result: ConnectionTestResult | null
  /** The draft changed after this result was recorded. */
  stale: boolean
  running: boolean
  /** Test results here always belong to the unsaved modal draft. */
  draft?: boolean
}

/**
 * Layered draft-test result (LG-104/LG-110).
 *
 * The Test button lives in the modal footer; this panel only reports the
 * result. A draft result is never persisted into the Connection or its saved
 * test history, so it is explicitly labelled and can never be mistaken for a
 * saved revision's verified status. Raw layer diagnostics stay collapsed.
 */
export function ConnectionTestPanel({
  result,
  stale,
  running,
  draft = true,
}: ConnectionTestPanelProps) {
  if (running) {
    return (
      <div className="lg-test" aria-live="polite">
        <p className="lg-field__hint" role="status">
          Running a draft test. Nothing is saved and no model request is made by
          opening this form.
        </p>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="lg-test">
        <p className="lg-field__hint">
          No draft test has been run. Test uses the current unsaved values without
          saving them; saving is never the same as a passing test.
        </p>
      </div>
    )
  }

  return (
    <div className="lg-test" aria-live="polite">
      <div className="lg-test__overall">
        <StatusBadge kind={overallKind(result.overall)}>
          {result.overall}
        </StatusBadge>
        {draft ? <StatusBadge kind="neutral">draft · not saved</StatusBadge> : null}
        {stale ? <StatusBadge kind="warning">stale</StatusBadge> : null}
      </div>
      <dl className="lg-test__meta">
        <div>
          <dt>model</dt>
          <dd>{result.model ?? '—'}</dd>
        </div>
        <div>
          <dt>upstream</dt>
          <dd>{result.base_url_host ?? '—'}</dd>
        </div>
        <div>
          <dt>finished</dt>
          <dd>{result.finished_at}</dd>
        </div>
      </dl>
      <details className="lg-disclosure">
        <summary className="lg-disclosure__summary">Layer details</summary>
        <div className="lg-disclosure__body">
          <dl className="lg-test__meta">
            <div>
              <dt>draft connection</dt>
              <dd>{result.connection_id || 'not saved'}</dd>
            </div>
            <div>
              <dt>saved revision</dt>
              <dd>{result.connection_revision ?? '—'}</dd>
            </div>
            <div>
              <dt>credential version</dt>
              <dd>{result.credential_version ?? '—'}</dd>
            </div>
          </dl>
          <ul className="lg-test__layers">
            {result.layers.map((layer: TestLayer) => (
              <li key={layer.name} className="lg-test__layer">
                <StatusBadge kind={layerKind(layer.status)}>
                  {layer.status}
                </StatusBadge>
                <span className="lg-test__layer-name">{layer.name}</span>
                <span className="lg-card__path">{layer.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      </details>
      {stale ? (
        <p className="lg-notice" role="status">
          This result belongs to an earlier version of the draft. It was not
          applied to the saved connection; run Test again after your changes.
        </p>
      ) : null}
      <p className="lg-field__hint">
        A draft result is not promoted to the saved connection's test status.
        Only the backend's persisted status is shown in the list after Save.
      </p>
    </div>
  )
}
