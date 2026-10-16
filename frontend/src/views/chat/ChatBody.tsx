import { useEffect, useRef, useState, type ChangeEvent } from 'react'

import { getRuntimeToken } from '../../api/auth'
import { type ChatApi, type ResolvedSourceBindingsData } from '../../api/chat'
import {
  createSourcesApi,
  type SourcesApi,
  type SourcesRuntimeConfig,
} from '../../api/sources'
import type { Attachment } from '../../api/types'
import { useShell } from '../../app/ShellProvider'
import { useAuth } from '../../app/AuthProvider'
import { draftKey } from '../../app/uiState'
import { ChatComposer } from '../../components/ChatComposer'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Icon } from '../../components/icons'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'
import { ChatMaterialIntake } from './ChatMaterialIntake'
import { ChatSourcePicker } from './ChatSourcePicker'
import { ChatSourceSearch } from './ChatSourceSearch'
import { ChatSources } from './ChatSources'
import { useChat } from './useChat'
import { useChatMaterials } from './useChatMaterials'
import { useChatSelection } from './useChatSelection'

export interface ChatBodyProps {
  /** `main` = Chat view body; `rail` = right column on other views. */
  variant: 'main' | 'rail'
  onRequestClose?: () => void
  /** Injectable for tests; defaults to the real `/conversations|/tasks` endpoints. */
  api?: ChatApi
  /** Injectable sources client; defaults to the real `/sources|/search` endpoints. */
  sourcesApi?: SourcesApi
  /** Runtime token source for protected material writes. */
  sourcesRuntime?: SourcesRuntimeConfig
}

interface PendingAttachment {
  path: string
  media_type: string | null
}

/**
 * The single Chat surface (LG-013; docs/05 §3, design.md §2).
 *
 * The Chat view body and the shell's right rail render this same component, so
 * exactly one conversation is ever shown and no second session is created. It
 * reads the real global/Task message history, sends through the frozen
 * endpoints (keeping the draft on failure), and links a delivery reply to its
 * newly created Task so the caller can open the real Board state.
 */
export function ChatBody({ variant, onRequestClose, api, sourcesApi, sourcesRuntime }: ChatBodyProps) {
  const { state, dispatch } = useShell()
  const { isTeam, requireLogin } = useAuth()
  const taskRef = state.taskRef
  const chat = useChat(
    { taskRef },
    api,
    // Team mode polls the global conversation only; single-user mode passes no
    // interval so the existing behavior is byte-for-byte unchanged (LG-050 §7).
    isTeam ? { pollIntervalMs: 3000, onUnauthorized: requireLogin } : {},
  )
  const resolvedSourcesApi =
    sourcesApi ?? createSourcesApi(sourcesRuntime ?? { getApiToken: getRuntimeToken })
  const materials = useChatMaterials(resolvedSourcesApi)
  const selection = useChatSelection(taskRef)
  const [materialNotice, setMaterialNotice] = useState<string | null>(null)
  // Resolved source bindings for the most recent send in this scope, so the
  // freshly returned reply can show its Sources before/without a reload.
  const [lastSendSources, setLastSendSources] = useState<ResolvedSourceBindingsData | null>(null)
  const key = draftKey(taskRef)
  const draft = state.drafts[key] ?? ''
  const [notice, setNotice] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [hasNewMessages, setHasNewMessages] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const prevCountRef = useRef(0)

  // Scope change (including Task switch) drops any transient reply Sources so it
  // can never leak across Task boundaries (docs/10 §1, §8).
  useEffect(() => {
    setLastSendSources(null)
    // A scope switch starts at the latest message, not a stale "new messages"
    // badge held over from the previous conversation.
    atBottomRef.current = true
    prevCountRef.current = 0
    setHasNewMessages(false)
  }, [taskRef])

  useEffect(() => {
    const list = listRef.current
    if (!list) return
    const grew = chat.messages.length > prevCountRef.current
    prevCountRef.current = chat.messages.length
    if (!grew) return
    // Never yank the viewport while the user is reading history: only auto-scroll
    // when already near the bottom, otherwise offer a "new messages" entry
    // (design.md §5). Incremental polling must not disturb the draft or scroll.
    if (atBottomRef.current) {
      list.scrollTop = list.scrollHeight
      setHasNewMessages(false)
    } else {
      setHasNewMessages(true)
    }
  }, [chat.messages.length])

  const handleScroll = () => {
    const list = listRef.current
    if (!list) return
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight <= 48
    atBottomRef.current = atBottom
    if (atBottom) setHasNewMessages(false)
  }

  const scrollToBottom = () => {
    const list = listRef.current
    if (!list) return
    list.scrollTop = list.scrollHeight
    atBottomRef.current = true
    setHasNewMessages(false)
  }

  const authorLabel = (message: (typeof chat.messages)[number]): string => {
    if (!isTeam) return message.role === 'user' ? 'You' : message.role
    // Team mode: the server writes the real author; legacy rows without one are
    // shown as Unknown rather than inventing a speaker (LG-050 §5).
    if (message.role === 'user') return message.author?.username ?? 'Unknown'
    if (message.role === 'assistant') return message.author?.username ?? 'Bot'
    return message.author?.username ?? message.role
  }

  const scopeLabel = taskRef ?? 'Global'

  const openSourceInFiles = (sourceId: string) => {
    // Meaningful backlink: open the real material in Files, keep the Task scope.
    dispatch({ type: 'selectItem', itemRef: `source:${sourceId}` })
    dispatch({ type: 'setView', view: 'files' })
  }

  const handleAddAttachment = (event: ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value.trim()
    if (!value) return
    setAttachments((current) => [
      ...current,
      { path: value, media_type: guessMediaType(value) },
    ])
    setAttachmentError(null)
    event.target.value = ''
  }

  const handleSubmit = async () => {
    if (!draft.trim()) return
    const payload = attachments.map<Attachment>((item) => ({
      path: item.path,
      media_type: item.media_type,
    }))
    const selectedRefs = selection.requestRefs
    setNotice(null)
    try {
      const outcome = await chat.send(draft, payload, selectedRefs)
      dispatch({ type: 'setDraft', key, value: '' })
      setAttachments([])
      // Implementation choice (docs/10 §8): clear the selection once the rule
      // backend accepts the send, because the refs are now bound to that
      // message; a failed send keeps them so an explicit retry reuses them.
      if (selectedRefs && selectedRefs.length > 0) selection.clear()
      setLastSendSources(outcome.resolvedSources)
      if (outcome.kind === 'recorded') {
        // Team-mode plain message: persisted for the team only, no bot reply.
        setNotice('Shared with the team.')
      } else if (outcome.createdTaskRef) {
        setNotice(`Created Task ${outcome.createdTaskRef}. Opening its Board scope.`)
        dispatch({ type: 'selectTask', taskRef: outcome.createdTaskRef })
      } else if (outcome.reply) {
        setNotice(null)
      }
    } catch {
      // Real error is rendered below; the draft stays so nothing is lost.
      setNotice('Not sent — see the error below. Your draft and attachments are kept.')
    }
  }

  return (
    <section
      className={`lg-chat lg-chat--${variant}`}
      aria-label={variant === 'main' ? 'Chat workspace' : 'Chat panel'}
    >
      <div className="lg-chat__header">
        <div>
          <h2 className="lg-chat__title">Chat</h2>
          <span className="lg-chat__subtitle">
            Scope: {scopeLabel}
            {taskRef ? (
              <button
                type="button"
                className="lg-link-button"
                onClick={() => dispatch({ type: 'selectTask', taskRef: null })}
              >
                Global
              </button>
            ) : null}
          </span>
        </div>
        {onRequestClose ? (
          <button
            type="button"
            className="lg-icon-button"
            onClick={onRequestClose}
            aria-label="Close chat panel"
          >
            <Icon name="close" />
          </button>
        ) : null}
      </div>

      <div
        className="lg-chat__messages"
        aria-label="Conversation messages"
        ref={listRef}
        onScroll={handleScroll}
      >
        {chat.error ? (
          <ErrorState
            title={chat.error.httpStatus === 404 ? 'Scope not found' : 'Could not load messages'}
            message={chat.error.message}
            code={chat.error.code}
            retryable={chat.error.retryable}
            requestId={chat.error.requestId}
            onRetry={chat.refresh}
          />
        ) : null}
        {!chat.error && chat.loading ? (
          <EmptyState title="Loading conversation…">Reading {scopeLabel} history.</EmptyState>
        ) : null}
        {!chat.error && !chat.loading && chat.messages.length === 0 ? (
          <EmptyState title="No messages yet">
            {taskRef
              ? 'Describe a change to continue this Task, or ask a question.'
              : 'Describe a goal to create a Task, or ask a question. Plain questions are answered without recruiting a team.'}
          </EmptyState>
        ) : null}
        {chat.messages.map((message) => (
          <article
            key={message.message_id}
            className={`lg-message lg-message--${message.role === 'user' ? 'user' : 'assistant'}`}
          >
            <div className="lg-message__meta">
              <span>{authorLabel(message)}</span>
              {message.at ? <span>{message.at}</span> : null}
              {message.resource_result?.status ? (
                <StatusBadge kind="neutral">
                  resource: {message.resource_result.status}
                </StatusBadge>
              ) : null}
            </div>
            <div className="lg-message__bubble">
              <MarkdownViewer content={message.content} />
            </div>
            {message.attachments.length > 0 ? (
              <ul className="lg-chat__attachments" aria-label="Attachments">
                {message.attachments.map((attachment) => (
                  <li key={attachment.path}>
                    <Icon name="files" size={14} />
                    <span className="lg-card__path">{attachment.path}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            {/* Persisted reply bindings (legacy rows have no `data` ⇒ nothing). */}
            <ChatSources data={message.data} onOpen={openSourceInFiles} />
          </article>
        ))}
      </div>

      <footer className="lg-chat__footer">
        {hasNewMessages ? (
          <button
            type="button"
            className="lg-button lg-chat__new-messages"
            onClick={scrollToBottom}
          >
            New messages ↓
          </button>
        ) : null}
        {notice ? (
          <p className="lg-notice" role="status">
            {notice}
          </p>
        ) : null}
        {chat.sendError ? (
          <p className="lg-notice lg-notice--error" role="alert">
            Send failed: {chat.sendError.message}{' '}
            <span className="lg-card__path">({chat.sendError.code})</span>
          </p>
        ) : null}
        {attachmentError ? (
          <p className="lg-notice lg-notice--error" role="alert">
            {attachmentError}
          </p>
        ) : null}
        <ChatMaterialIntake
          materials={materials.materials}
          busy={materials.busy}
          scopeLabel={scopeLabel}
          canWrite
          notice={materialNotice}
          onUploadFiles={(files) => {
            setMaterialNotice(null)
            void materials.uploadFiles(files, { taskRef })
          }}
          onRecordLink={(url) => {
            setMaterialNotice(null)
            materials.recordLink(url, { taskRef }).catch((cause: unknown) => {
              setMaterialNotice(cause instanceof Error ? cause.message : 'Invalid link')
            })
          }}
          onRefresh={(requestId) => void materials.refresh(requestId)}
          onDismiss={materials.dismiss}
        />
        <ChatSourceSearch
          api={resolvedSourcesApi}
          taskRef={taskRef}
          onOpen={(sourceId) => openSourceInFiles(sourceId)}
        />
        {/* Reply-time Sources from the just-returned send (not yet reloaded). */}
        {lastSendSources ? (
          <ChatSources data={lastSendSources} onOpen={openSourceInFiles} />
        ) : null}
        <ChatSourcePicker
          api={resolvedSourcesApi}
          taskRef={taskRef}
          selection={selection.selection}
          atLimit={selection.atLimit}
          onToggle={selection.toggle}
          onRemove={selection.remove}
          onClear={selection.clear}
          disabled={chat.sending}
        />
        {attachments.length > 0 ? (
          <ul className="lg-chat__chip-row" aria-label="Pending attachments">
            {attachments.map((attachment, index) => (
              <li key={`${attachment.path}-${index}`} className="lg-chip">
                <span className="lg-card__path">{attachment.path}</span>
                <button
                  type="button"
                  className="lg-icon-button"
                  aria-label={`Remove attachment ${attachment.path}`}
                  onClick={() =>
                    setAttachments((current) => current.filter((_, i) => i !== index))
                  }
                >
                  <Icon name="close" size={12} />
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <label className="lg-chat__attach">
          <span className="lg-visually-hidden">Reference a file by path</span>
          <input
            type="text"
            className="lg-input"
            placeholder="Attach file path (workspace-relative)…"
            aria-label="Attach file path"
            onChange={handleAddAttachment}
          />
        </label>
        <ChatComposer
          value={draft}
          onChange={(value) => {
            dispatch({ type: 'setDraft', key, value })
            if (notice) setNotice(null)
          }}
          onSubmit={handleSubmit}
          scopeLabel={scopeLabel}
          hint={
            isTeam
              ? 'Shared with the team · start with @bot to ask the assistant · Enter to send'
              : undefined
          }
          disabled={chat.sending}
          disabledReason="A message is being sent…"
        />
      </footer>
    </section>
  )
}

function guessMediaType(path: string): string | null {
  // Reference-only attachment classification; no bytes leave the browser.

  const lower = path.toLowerCase()
  if (lower.endsWith('.md')) return 'text/markdown'
  if (lower.endsWith('.json')) return 'application/json'
  if (lower.endsWith('.txt')) return 'text/plain'
  if (lower.endsWith('.png')) return 'image/png'
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg'
  return null
}
