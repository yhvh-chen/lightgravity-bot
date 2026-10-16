import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'

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
import { draftKey, type ChatChannel } from '../../app/uiState'
import { ChatComposer } from '../../components/ChatComposer'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Icon } from '../../components/icons'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'
import { ChatMaterialIntake } from './ChatMaterialIntake'
import { ChatSourcePicker } from './ChatSourcePicker'
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
  const { isTeam, requireLogin, personalChatAvailable } = useAuth()
  const taskRef = state.taskRef
  // LG-054: single-user mode has no team, so the only channel is the legacy
  // personal/global one.  In team mode the user picks; the default is Team.
  const channel: ChatChannel = isTeam ? (state.chatChannel === 'personal' && personalChatAvailable ? 'personal' : 'team') : 'personal'
  const privatePersonal = isTeam && channel === 'personal'
  // A private Personal conversation never carries Task scope; Team tasks stay
  // shared Team conversations.
  const effectiveTaskRef = privatePersonal ? null : taskRef
  const scope = { taskRef: effectiveTaskRef, personal: privatePersonal }
  const chat = useChat(
    scope,
    api,
    // Team mode polls the active global/private conversation; single-user mode
    // passes no interval so the existing behavior is byte-for-byte unchanged.
    isTeam ? { pollIntervalMs: 3000, onUnauthorized: requireLogin } : {},
  )
  const resolvedSourcesApi = useMemo(
    () => sourcesApi ?? createSourcesApi(sourcesRuntime ?? { getApiToken: getRuntimeToken }),
    [sourcesApi, sourcesRuntime],
  )
  const materials = useChatMaterials(resolvedSourcesApi)
  const selection = useChatSelection(effectiveTaskRef)
  const [extrasOpen, setExtrasOpen] = useState(false)
  const [materialNotice, setMaterialNotice] = useState<string | null>(null)
  // Resolved source bindings for the most recent send in this scope, so the
  // freshly returned reply can show its Sources before/without a reload.
  const [lastSendSources, setLastSendSources] = useState<ResolvedSourceBindingsData | null>(null)
  const key = draftKey(effectiveTaskRef, isTeam ? channel : null)
  const draft = state.drafts[key] ?? ''
  const activeConversation = useRef(key)
  const conversationGeneration = useRef(0)
  if (activeConversation.current !== key) {
    activeConversation.current = key
    conversationGeneration.current += 1
  }
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const [notice, setNotice] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [hasNewMessages, setHasNewMessages] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const prevCountRef = useRef(0)

  // Scope change (including Task/channel switch) drops any transient reply
  // Sources so it can never leak across conversation boundaries (docs/10 §1).
  useEffect(() => {
    setLastSendSources(null)
    selection.clear()
    setAttachments([])
    setExtrasOpen(false)
    // A scope switch starts at the latest message, not a stale "new messages"
    // badge held over from the previous conversation.
    atBottomRef.current = true
    prevCountRef.current = 0
    setHasNewMessages(false)
  }, [effectiveTaskRef, privatePersonal])

  useEffect(() => { setNotice(null) }, [privatePersonal])

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

  const scopeLabel = effectiveTaskRef ?? (privatePersonal ? 'Personal' : 'Global')

  const switchToTeam = () => {
    setNotice(null)
    dispatch({ type: 'setChatChannel', channel: 'team' })
  }
  const switchToPersonal = () => {
    if (!isTeam || !personalChatAvailable) return
    // Privacy: leaving Team for Personal drops any Task scope so a shared task
    // context is never carried into the private conversation.
    setNotice(null)
    dispatch({ type: 'setChatChannel', channel: 'personal' })
    dispatch({ type: 'selectTask', taskRef: null })
  }

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
    const requestGeneration = conversationGeneration.current
    const payload = (privatePersonal ? [] : attachments).map<Attachment>((item) => ({
      path: item.path,
      media_type: item.media_type,
    }))
    const selectedRefs = privatePersonal ? undefined : selection.requestRefs
    setNotice(null)
    try {
      const outcome = await chat.send(draft, payload, selectedRefs)
      if (!mounted.current) return
      dispatch({ type: 'setDraft', key, value: '' })
      if (requestGeneration !== conversationGeneration.current) return
      setAttachments([])
      // Implementation choice (docs/10 §8): clear the selection once the rule
      // backend accepts the send, because the refs are now bound to that
      // message; a failed send keeps them so an explicit retry reuses them.
      if (selectedRefs && selectedRefs.length > 0) selection.clear()
      setLastSendSources(outcome.resolvedSources)
      if (outcome.kind === 'recorded') {
        // Team-mode plain message: persisted for the team only, no bot reply.
        setNotice('Shared with the team.')
      } else if (outcome.kind === 'switch_to_team') {
        setNotice('Personal is private and chat-only. Switch to Team to create a task or run delivery — nothing was created.')
      } else if (outcome.kind === 'unavailable') {
        setNotice('Personal chat needs a configured model. Configure one in Settings, or use Team.')
      } else if (outcome.createdTaskRef) {
        setNotice(`Created Task ${outcome.createdTaskRef}. Opening its Board scope.`)
        dispatch({ type: 'selectTask', taskRef: outcome.createdTaskRef })
      } else if (outcome.reply) {
        setNotice(null)
      }
    } catch {
      // A response for a departed channel must not change the active composer.
      if (!mounted.current || requestGeneration !== conversationGeneration.current) return
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
            {effectiveTaskRef ? `Task ${effectiveTaskRef}` : privatePersonal ? 'Private' : 'Conversation'}
            {effectiveTaskRef ? (
              <button
                type="button"
                className="lg-link-button"
                onClick={() => dispatch({ type: 'selectTask', taskRef: null })}
              >
                {isTeam ? 'Team conversation' : 'Conversation'}
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

      <div className="lg-chat__channels">
        <div className="lg-chat__channels-tabs" role="tablist" aria-label="Conversation channel">
          <button
            type="button"
            role="tab"
            aria-selected={channel === 'personal'}
            disabled={isTeam && !personalChatAvailable}
            title={isTeam && !personalChatAvailable ? 'Personal requires backend contract >= 1.14 and the personal_chat capability' : undefined}
            className={`lg-button${channel === 'personal' ? ' lg-button--primary' : ''}`}
            onClick={switchToPersonal}
          >
            Personal
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={channel === 'team'}
            disabled={!isTeam}
            title={!isTeam ? 'Enable team mode on the backend to use the shared team conversation' : undefined}
            className={`lg-button${channel === 'team' ? ' lg-button--primary' : ''}`}
            onClick={switchToTeam}
          >
            Team
          </button>
        </div>
        <p className="lg-chat__channel-note">
          {isTeam && !personalChatAvailable
            ? 'Personal is unavailable on this backend. Update to contract 1.14 or later with personal_chat enabled; shared Team conversations remain available.'
            : privatePersonal
            ? 'Private to you and chat-only — no shared Task, materials, or team messages.'
            : !isTeam
              ? 'Team mode is not enabled on this backend; enable team mode to use the shared team conversation.'
              : effectiveTaskRef
                ? 'Shared Team Task conversation.'
                : 'Shared with the team; start with @bot to ask the assistant.'}
        </p>
      </div>

      <div
        className="lg-chat__messages"
        aria-label="Conversation messages"
        ref={listRef}
        onScroll={handleScroll}
      >
        {chat.error ? (
          <ErrorState
            title={chat.error.httpStatus === 404
              ? effectiveTaskRef ? 'Task conversation unavailable' : 'Conversation service unavailable'
              : 'Could not load messages'}
            message={chat.error.message}
            code={chat.error.code}
            retryable={chat.error.retryable}
            requestId={chat.error.requestId}
            onRetry={chat.refresh}
          />
        ) : null}
        {chat.error?.httpStatus === 404 ? (
          <div className="lg-chat__recovery">
            <p>Your draft is kept. {effectiveTaskRef ? 'The task or conversation endpoint may no longer be available.' : 'Check that the server supports conversations.'}</p>
            <button type="button" className="lg-button" onClick={() => dispatch({ type: 'setView', view: 'files' })}>Choose task in Files</button>
            {effectiveTaskRef ? <button type="button" className="lg-button" onClick={() => dispatch({ type: 'selectTask', taskRef: null })}>Return to conversation</button> : null}
          </div>
        ) : null}
        {!chat.error && chat.loading ? (
          <EmptyState title="Loading conversation…">Reading {scopeLabel} history.</EmptyState>
        ) : null}
        {!chat.error && !chat.loading && chat.messages.length === 0 ? (
          <EmptyState title="No messages yet">
            {effectiveTaskRef
              ? 'Describe a change to continue this Task, or ask a question.'
              : privatePersonal
                ? 'Ask a private question. Personal is chat-only; tasks and shared materials live in Team.'
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
        {/* Reply-time Sources from the just-returned send (not yet reloaded). */}
        {!privatePersonal && lastSendSources ? (
          <ChatSources data={lastSendSources} onOpen={openSourceInFiles} />
        ) : null}
        {!privatePersonal && attachments.length > 0 ? (
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
        {!privatePersonal ? (
          <div className="lg-chat__tools">
            <button type="button" className="lg-button" aria-label="Add attachments and materials" aria-expanded={extrasOpen} aria-controls="lg-chat-extras" onClick={() => setExtrasOpen(!extrasOpen)}>+</button>
            {selection.selection.length > 0 && !extrasOpen ? <span>{selection.selection.length} selected material(s) <button type="button" className="lg-link-button" onClick={() => setExtrasOpen(true)}>Review</button></span> : null}
            {!extrasOpen && materials.materials.length > 0 ? <span aria-live="polite">{materials.busy ? 'Uploading…' : `${materials.materials.length} upload receipt(s)`} <button type="button" className="lg-link-button" onClick={() => setExtrasOpen(true)}>View uploads</button></span> : null}
          </div>
        ) : (
          <p className="lg-chat__tools-hint">
            Shared materials and task delivery are available in Team.
          </p>
        )}
        {!privatePersonal ? <div id="lg-chat-extras" hidden={!extrasOpen}>
        <ChatMaterialIntake
          materials={materials.materials}
          busy={materials.busy}
          scopeLabel={scopeLabel}
          canWrite
          notice={materialNotice}
          onUploadFiles={(files) => {
            setMaterialNotice(null)
            void materials.uploadFiles(files, { taskRef: effectiveTaskRef })
          }}
          onRecordLink={(url) => {
            setMaterialNotice(null)
            materials.recordLink(url, { taskRef: effectiveTaskRef }).catch((cause: unknown) => {
              setMaterialNotice(cause instanceof Error ? cause.message : 'Invalid link')
            })
          }}
          onRefresh={(requestId) => void materials.refresh(requestId)}
          onDismiss={materials.dismiss}
        />
        <ChatSourcePicker
          api={resolvedSourcesApi}
          taskRef={effectiveTaskRef}
          selection={selection.selection}
          atLimit={selection.atLimit}
          onToggle={selection.toggle}
          onRemove={selection.remove}
          onClear={selection.clear}
          disabled={chat.sending}
        />
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
        </div> : null}
        <ChatComposer
          value={draft}
          onChange={(value) => {
            dispatch({ type: 'setDraft', key, value })
            if (notice) setNotice(null)
          }}
          onSubmit={handleSubmit}
          scopeLabel={scopeLabel}
          hint={
            privatePersonal
              ? 'Private to you · chat-only · Enter to send'
              : isTeam
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
