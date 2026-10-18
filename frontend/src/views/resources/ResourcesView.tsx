import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'

import { ApiError } from '../../api/client'
import {
  categoryById,
  categoryByKind,
  createResourcesApi,
  isResourceKind,
  NAV_RESOURCE_CATEGORIES,
  type ResourceDetail,
  type ResourceKind,
  type ResourceChangeResult,
  type ResourceReference,
  type ResourceSummary,
  type ResourcesApi,
} from '../../api/resources'
import type { ViewId } from '../../app/navigation'
import { useShell } from '../../app/ShellProvider'
import { settingsConnectionRef } from '../../app/uiState'
import { DetailHeader } from '../../components/DetailHeader'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { ResourceCard } from '../../components/ResourceCard'
import { StatusBadge } from '../../components/StatusBadge'
import { availabilityBadge } from './availability'
import { Diagnostics } from './Diagnostics'
import { clearTeamReturn, readTeamReturn } from '../team/returnState'
import './resources.css'

export interface ResourcesViewProps {
  api?: ResourcesApi
  selectedItemRef?: string | null
  navigate?: (view: ViewId) => void
  selectItem?: (ref: string | null) => void
}

interface ResourceRef {
  kind: ResourceKind
  id: string
}

/** `resources:<kind>:<id>` is the in-app reference to one resource detail. */
function parseResourceRef(ref: string | null | undefined): ResourceRef | null {
  if (!ref || !ref.startsWith('resources:')) return null
  const parts = ref.split(':')
  if (parts.length < 3) return null
  const kind = parts[1]
  const id = parts.slice(2).join(':')
  if (!isResourceKind(kind) || !id) return null
  return { kind, id }
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) return value.length > 0 ? value.map(formatValue).join(', ') : '—'
  return JSON.stringify(value)
}

const HIDDEN_ENTITY_KEYS = new Set(['schema', 'kind', 'id', 'revision', 'title'])

/**
 * Resources (owner LG-015; docs/05 §6.1, design.md §5 Resources).
 *
 * Seven vertical categories read the real `/api/v1/resources/{kind}` endpoints.
 * Detail follows the stable order title/status → key fields → references →
 * Markdown body → diagnostics, and keeps declared, parsed, dependency and
 * runtime availability separate (unknown is never green).  Session Profiles
 * explicitly state they are templates, not live conversations.  Connections
 * only navigate to Settings, which owns the same entity; no second model list
 * is built.  Non-connection resources get a narrow, validated controlled-change
 * panel (title/enabled/body) that writes through the Store with the revision.
 */
export function ResourcesView(props: ResourcesViewProps = {}) {
  const shell = useShell()
  const api = useMemo(() => props.api ?? createResourcesApi(), [props.api])
  const selectedItemRef =
    props.selectedItemRef !== undefined ? props.selectedItemRef : shell.state.selectedItemRef
  const navigate =
    props.navigate ?? ((view: ViewId) => shell.dispatch({ type: 'setView', view }))
  const selectItem =
    props.selectItem ??
    ((ref: string | null) => shell.dispatch({ type: 'selectItem', itemRef: ref }))

  const parsedRef = parseResourceRef(selectedItemRef)
  const category =
    (parsedRef ? categoryByKind(parsedRef.kind) : null) ??
    categoryById(selectedItemRef) ??
    NAV_RESOURCE_CATEGORIES[0]
  const selectedId = parsedRef && parsedRef.kind === category.kind ? parsedRef.id : null

  const [items, setItems] = useState<ResourceSummary[] | null>(null)
  const [detail, setDetail] = useState<ResourceDetail | null>(null)
  const [listError, setListError] = useState<ApiError | null>(null)
  const [detailError, setDetailError] = useState<ApiError | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [listKey, setListKey] = useState(0)
  const [detailKey, setDetailKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setListError(null)
    api
      .listResources(category.kind, controller.signal)
      .then((result) => {
        if (cancelled) return
        setItems(result.items)
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        setItems(null)
        setListError(toApiError(cause))
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, category.kind, listKey])

  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      setDetailError(null)
      return
    }
    let cancelled = false
    const controller = new AbortController()
    setDetailLoading(true)
    setDetailError(null)
    api
      .getResource(category.kind, selectedId, controller.signal)
      .then((loaded) => {
        if (cancelled) return
        setDetail(loaded)
      })
      .catch((cause: unknown) => {
        if (cancelled || controller.signal.aborted) return
        setDetail(null)
        setDetailError(toApiError(cause))
      })
      .finally(() => {
        if (!cancelled) setDetailLoading(false)
      })
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [api, category.kind, selectedId, detailKey])

  const selectResource = useCallback(
    (id: string) => selectItem(`resources:${category.kind}:${id}`),
    [category.kind, selectItem],
  )


  const teamReturn = readTeamReturn()

  return (
    <div className="lg-resources-view">
      <DetailHeader
        title="Resources"
        badges={<StatusBadge kind="accent">{category.label}</StatusBadge>}
        meta={[
          { label: 'category', value: category.id },
          { label: 'source', value: `resources/${category.kind}` },
        ]}
        actions={
          teamReturn ? (
            <button
              type="button"
              className="lg-button"
              onClick={() => {
                clearTeamReturn()
                selectItem(teamReturn.itemRef)
                navigate('team')
              }}
            >
              Back to Team
            </button>
          ) : null
        }
      />

      <p className="lg-field__hint">{category.blurb}</p>

      {category.kind === 'conversation' ? (
        <p className="lg-notice" role="note">
          Session Profiles are conversation <strong>configuration templates</strong>. They are not
          live conversations; real user conversations live in Chat and member SDK sessions live in
          the recruited member detail.
        </p>
      ) : null}

      <div className="lg-resources">
        <section className="lg-resources__list" aria-label={`${category.label} list`}>
          <div className="lg-resources__list-head">
            <span className="lg-field__label">
              {items?.length ?? 0} {category.label}
            </span>
            <button
              type="button"
              className="lg-button"
              onClick={() => setListKey((key) => key + 1)}
            >
              Refresh
            </button>
          </div>
          {listError ? (
            <ErrorState
              title={`Could not load ${category.label}`}
              message={listError.message}
              code={listError.code}
              retryable={listError.retryable}
              requestId={listError.requestId}
              onRetry={() => setListKey((key) => key + 1)}
            />
          ) : items === null ? (
            <p className="lg-field__hint" role="status">
              Loading {category.label}…
            </p>
          ) : items.length === 0 ? (
            <EmptyState title={`No ${category.label} yet`}>
              <p>
                No files were found under{' '}
                <span className="lg-card__path">resources/{category.kind}</span>.
              </p>
            </EmptyState>
          ) : (
            <ul className="lg-resources__items">
              {items.map((item) => {
                const badge = availabilityBadge(item.availability)
                return (
                  <li key={item.id}>
                    <ResourceCard
                      title={item.title}
                      kind={item.kind}
                      path={item.id}
                      availability={{ kind: badge.kind, label: badge.label }}
                      onOpen={() => selectResource(item.id)}
                    />
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section className="lg-resources__detail" aria-label="Resource detail">
          {detailError ? (
            <ErrorState
              title="Could not load resource"
              message={detailError.message}
              code={detailError.code}
              retryable={detailError.retryable}
              requestId={detailError.requestId}
              onRetry={() => setDetailKey((key) => key + 1)}
            />
          ) : detailLoading && !detail ? (
            <p className="lg-field__hint" role="status">
              Loading detail…
            </p>
          ) : detail ? (
            <ResourceDetailPanel
              key={`${detail.kind}:${detail.id}:${detail.revision}`}
              detail={detail}
              api={api}
              taskRef={shell.state.taskRef}
              onEdited={() => {
                setDetailKey((key) => key + 1)
                setListKey((key) => key + 1)
              }}
              onNavigateReference={(kind, ref) => {
                if (kind === 'connection') {
                  // LG-103: every Connection reference opens the one Settings
                  // management surface at the matching stable id.
                  selectItem(settingsConnectionRef(ref))
                  navigate('settings')
                  return
                }
                selectItem(`resources:${kind}:${ref}`)
              }}
              onOpenSettings={(connectionId) => {
                // Carry the concrete Connection id so Settings selects the same
                // record; the Task scope is preserved by the shell.
                selectItem(settingsConnectionRef(connectionId))
                navigate('settings')
              }}
              onOpenChat={() => navigate('tasks')}
            />
          ) : (
            <EmptyState title="Select a resource">
              <p>Fields, references, Markdown body and diagnostics appear here.</p>
            </EmptyState>
          )}
        </section>
      </div>


    </div>
  )
}

function ResourceDetailPanel({
  detail,
  api,
  taskRef,
  onEdited,
  onNavigateReference,
  onOpenSettings,
  onOpenChat,
}: {
  detail: ResourceDetail
  api: ResourcesApi
  taskRef: string | null
  onEdited: () => void
  onNavigateReference: (kind: string, ref: string) => void
  onOpenSettings: (connectionId: string) => void
  onOpenChat: () => void
}) {
  const badge = availabilityBadge(detail.availability)
  const entries = Object.entries(detail.entity).filter(
    ([key, value]) =>
      !HIDDEN_ENTITY_KEYS.has(key) && value !== null && value !== undefined && value !== '',
  )

  return (
    <div>
      <DetailHeader
        title={detail.title}
        badges={
          <>
            <StatusBadge kind={badge.kind} title={badge.title}>
              {badge.label}
            </StatusBadge>
            {!detail.enabled ? <StatusBadge kind="neutral">disabled</StatusBadge> : null}
          </>
        }
        meta={[
          { label: 'kind', value: detail.kind },
          { label: 'id', value: detail.id },
          { label: 'revision', value: detail.revision === null ? '—' : String(detail.revision) },
        ]}
        actions={
          detail.kind === 'connection' ? (
            <button
              type="button"
              className="lg-button lg-button--primary"
              onClick={() => onOpenSettings(detail.id)}
            >
              Edit in Settings
            </button>
          ) : detail.kind === 'conversation' ? (
            <button type="button" className="lg-button" onClick={onOpenChat}>
              Open Chat
            </button>
          ) : null
        }
      />

      {detail.availability.reasons.length > 0 ? (
        <section className="lg-resource-block" aria-label="Availability">
          <h4 className="lg-section__title">Availability</h4>
          <ul className="lg-resource-reasons">
            {detail.availability.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
          <p className="lg-field__hint">
            Declared enabled, parsed schema, resolved dependencies and live health are different
            facts. Unknown means no live check was run.
          </p>
        </section>
      ) : null}

      <section className="lg-resource-block" aria-label="Fields">
        <h4 className="lg-section__title">Fields</h4>
        {entries.length === 0 ? (
          <p className="lg-field__hint">No additional frontmatter fields.</p>
        ) : (
          <dl className="lg-kv">
            {entries.map(([key, value]) => (
              <div className="lg-kv__row" key={key}>
                <dt>{key}</dt>
                <dd>{formatValue(value)}</dd>
              </div>
            ))}
          </dl>
        )}
        <p className="lg-field__hint">
          Unknown fields are preserved but never given execution semantics.
        </p>
      </section>

      <section className="lg-resource-block" aria-label="References">
        <h4 className="lg-section__title">References</h4>
        {detail.references.length === 0 ? (
          <p className="lg-field__hint">No outgoing references.</p>
        ) : (
          <ul className="lg-refs">
            {detail.references.map((reference) => (
              <ReferenceRow
                key={`${reference.field ?? ''}:${reference.kind}:${reference.ref}`}
                reference={reference}
                onNavigate={onNavigateReference}
              />
            ))}
          </ul>
        )}
        {detail.inbound_refs.length > 0 ? (
          <>
            <h5 className="lg-section__title">Referenced by</h5>
            <ul className="lg-refs">
              {detail.inbound_refs.map((inbound) => (
                <li key={`${inbound.from_kind}:${inbound.from_id}:${inbound.field}`}>
                  <span className="lg-card__path">
                    {inbound.from_kind}:{inbound.from_id}
                  </span>
                  <span className="lg-refs__field">{inbound.field}</span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      {detail.diagnostics.length > 0 ? <Diagnostics diagnostics={detail.diagnostics} /> : null}

      {detail.kind !== 'connection' ? (
        <ControlledChange detail={detail} api={api} taskRef={taskRef} onEdited={onEdited} />
      ) : (
        <section className="lg-resource-block" aria-label="Model connection">
          <h4 className="lg-section__title">Model &amp; credential</h4>
          <p className="lg-field__hint">
            This Connection is the same record Settings edits. Model, endpoint and credential value
            are changed there so there is only one connection authority; this category does not keep
            a second model list.
          </p>
        </section>
      )}

      <section className="lg-resource-block" aria-label="Body">
        <h4 className="lg-section__title">Body</h4>
        {detail.body.trim() ? (
          <MarkdownViewer content={detail.body} />
        ) : (
          <p className="lg-field__hint">No body content.</p>
        )}
      </section>
    </div>
  )
}

function ReferenceRow({
  reference,
  onNavigate,
}: {
  reference: ResourceReference
  onNavigate: (kind: string, ref: string) => void
}) {
  const navigable = isResourceKind(reference.kind)
  const label = (
    <>
      <span className="lg-card__path">
        {reference.kind}:{reference.ref}
      </span>
      <span className="lg-refs__field">{reference.field ?? ''}</span>
      <StatusBadge kind={reference.state === 'resolved' ? 'success' : 'error'}>
        {reference.state}
      </StatusBadge>
    </>
  )
  return (
    <li>
      {navigable ? (
        <button
          type="button"
          className="lg-refs__link"
          onClick={() => onNavigate(reference.kind, reference.ref)}
        >
          {label}
        </button>
      ) : (
        <span className="lg-refs__static">{label}</span>
      )}
    </li>
  )
}

type SaveState = 'idle' | 'saving' | 'saved' | 'conflict'

/**
 * Controlled change (docs/05 §6.2).
 *
 * The change is sent as a *structured proposal* attached to an authenticated
 * Task message; the coordinator validates it and calls `ResourceService.update`,
 * then records the actual result/conflict back into the Task conversation.  The
 * form never writes the resource file itself, and without a Task scope it only
 * guides the user instead of faking a shared-template edit.
 */
function ControlledChange({
  detail,
  api,
  taskRef,
  onEdited,
}: {
  detail: ResourceDetail
  api: ResourcesApi
  taskRef: string | null
  onEdited: () => void
}) {
  const [title, setTitle] = useState(detail.title)
  const [enabled, setEnabled] = useState(detail.enabled)
  const [body, setBody] = useState(detail.body)
  const [state, setState] = useState<SaveState>('idle')
  const [savedRevision, setSavedRevision] = useState<number | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const supportsEnabled = detail.kind !== 'skill'

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (detail.revision === null) return
    if (!taskRef) {
      setNotice(
        'Select a Task before changing a shared resource: the change is proposed in ' +
          'that Task chat and program-validated there. No change was written here.',
      )
      return
    }
    setState('saving')
    setError(null)
    setNotice(null)
    const patch: Record<string, unknown> = { title: title.trim() }
    if (supportsEnabled) patch.enabled = enabled
    try {
      const result = await api.proposeResourceChange(taskRef, {
        kind: detail.kind,
        id: detail.id,
        expected_revision: detail.revision,
        patch,
        body,
      })
      const status = result.data.status
      if (status === 'applied') {
        setState('saved')
        setSavedRevision(
          typeof result.data.revision === 'number' ? result.data.revision : detail.revision + 1,
        )
        onEdited()
      } else if (status === 'conflict') {
        setState('conflict')
        setError(proposalError(result))
        onEdited()
      } else {
        setState('idle')
        setError(proposalError(result))
      }
    } catch (cause) {
      setState('idle')
      setError(toApiError(cause))
    }
  }

  return (
    <section className="lg-resource-block" aria-label="Controlled change">
      <h4 className="lg-section__title">Controlled change</h4>
      <p className="lg-field__hint">
        Only title, enablement and the Markdown body can be changed here. The change is
        sent as a structured proposal in the current Task chat, program-validated (schema +
        references + revision) and written atomically. It affects future recruitment only —
        running members keep their pinned configuration and are never hot-swapped.
      </p>
      {notice ? (
        <p className="lg-notice" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <ErrorState
          title={state === 'conflict' ? 'Revision conflict' : 'Change rejected'}
          message={error.message}
          code={error.code}
          retryable={error.retryable}
          requestId={error.requestId}
        />
      ) : null}
      {state === 'conflict' ? (
        <p className="lg-field__hint">
          The resource changed elsewhere; the latest revision is reloaded. Review and submit again.
        </p>
      ) : null}
      {state === 'saved' ? (
        <p className="lg-notice" role="status">
          Applied through Task chat at revision {savedRevision ?? (detail.revision ?? 0) + 1}.
        </p>
      ) : null}
      <form className="lg-resource-form" onSubmit={handleSubmit}>
        <label className="lg-field">
          <span className="lg-field__label">Title</span>
          <input
            className="lg-field__input"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            autoComplete="off"
          />
        </label>
        {supportsEnabled ? (
          <label className="lg-field lg-field--inline">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => setEnabled(event.target.checked)}
            />
            <span className="lg-field__label">Enabled</span>
          </label>
        ) : null}
        <label className="lg-field">
          <span className="lg-field__label">Markdown body</span>
          <textarea
            className="lg-field__input lg-resource-form__body"
            value={body}
            onChange={(event) => setBody(event.target.value)}
            spellCheck={false}
            rows={6}
          />
        </label>
        <div className="lg-resource-form__actions">
          <button
            type="submit"
            className="lg-button lg-button--primary"
            disabled={state === 'saving'}
          >
            {state === 'saving' ? 'Saving…' : 'Save controlled change'}
          </button>
        </div>
      </form>
    </section>
  )
}

function proposalError(result: ResourceChangeResult): ApiError {
  const code =
    typeof result.data.error_code === 'string' ? result.data.error_code : 'invalid_request'
  return new ApiError({
    message: result.reply || 'Resource change was rejected',
    code,
    httpStatus: null,
    retryable: code === 'lock_conflict',
  })
}

function toApiError(cause: unknown): ApiError {
  if (cause instanceof ApiError) return cause
  return new ApiError({
    message: cause instanceof Error ? cause.message : 'Request failed',
    code: 'network_error',
    httpStatus: null,
    retryable: true,
  })
}
