import { useEffect, useRef, useState, type ChangeEvent } from 'react'

import { type ChatApi } from '../../api/chat'
import type { Attachment } from '../../api/types'
import { useShell } from '../../app/ShellProvider'
import { draftKey } from '../../app/uiState'
import { ChatComposer } from '../../components/ChatComposer'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Icon } from '../../components/icons'
import { MarkdownViewer } from '../../components/MarkdownViewer'
import { StatusBadge } from '../../components/StatusBadge'
import { useChat } from './useChat'

export interface ChatBodyProps {
  /** `main` = Chat view body; `rail` = right column on other views. */
  variant: 'main' | 'rail'
  onRequestClose?: () => void
  /** Injectable for tests; defaults to the real `/conversations|/tasks` endpoints. */
  api?: ChatApi
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
export function ChatBody({ variant, onRequestClose, api }: ChatBodyProps) {
  const { state, dispatch } = useShell()
  const taskRef = state.taskRef
  const chat = useChat({ taskRef }, api)
  const key = draftKey(taskRef)
  const draft = state.drafts[key] ?? ''
  const [notice, setNotice] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<PendingAttachment[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight
  }, [chat.messages.length])

  const scopeLabel = taskRef ?? 'Global'

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
    setNotice(null)
    try {
      const outcome = await chat.send(draft, payload)
      dispatch({ type: 'setDraft', key, value: '' })
      setAttachments([])
      if (outcome.createdTaskRef) {
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
              <span>{message.role === 'user' ? 'You' : message.role}</span>
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
          </article>
        ))}
      </div>

      <footer className="lg-chat__footer">
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
