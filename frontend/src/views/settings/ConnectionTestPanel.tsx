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
  /** Result revision/credential version no longer matches the connection. */
  stale: boolean
  running: boolean
  onRun: () => void
  /** Non-null explains why testing is disabled (e.g. unverified backend). */
  disabledReason: string | null
}

/**
 * Layered Test Connection results (docs/07 §5, design.md §5).
 *
 * Config, credential, SDK capability *declaration*, real network/model and the
 * optional tool/structured probes are shown separately: a network success is
 * never presented as "SDK capability verified". Stale results stay visible but
 * are clearly marked.
 */
export function ConnectionTestPanel({
  result,
  stale,
  running,
  onRun,
  disabledReason,
}: ConnectionTestPanelProps) {
  return (
    <div className="lg-test">
      <p className="lg-field__hint">
        A network test makes one minimal model request and may consume a small
        amount of model credit. The layers are reported separately; saving is not
        the same as passing.
      </p>
      <button
        type="button"
        className="lg-button lg-button--primary"
        onClick={onRun}
        disabled={running || disabledReason !== null}
        aria-busy={running}
      >
        {running ? 'Testing…' : 'Test connection'}
      </button>
      {disabledReason ? <p className="lg-field__hint">{disabledReason}</p> : null}

      {result ? (
        <div className="lg-test__result" aria-live="polite">
          <div className="lg-test__overall">
            <StatusBadge kind={overallKind(result.overall)}>
              {result.overall}
            </StatusBadge>
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
            <div>
              <dt>connection revision</dt>
              <dd>{result.connection_revision}</dd>
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
          {stale ? (
            <p className="lg-notice">
              This result was recorded for connection revision{' '}
              {result.connection_revision} and is no longer current. Run the test
              again after your changes.
            </p>
          ) : null}
        </div>
      ) : (
        <p className="lg-field__hint">No test has been run in this session.</p>
      )}
    </div>
  )
}
