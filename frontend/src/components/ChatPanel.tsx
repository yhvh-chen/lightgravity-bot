import { useState } from 'react'

import { useBackendStatus } from '../api/useBackendStatus'
import { MOCK_MESSAGES, MOCK_NOTICE } from '../app/layoutMock'
import { useShell } from '../app/ShellProvider'
import { draftKey } from '../app/uiState'
import { ChatComposer } from './ChatComposer'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'
import { Icon } from './icons'
import { MockBadge } from './StatusBadge'

export interface ChatPanelProps {
  /** `main` = Chat view body; `rail` = right column on other views. */
  variant: 'main' | 'rail'
  /** Present only when the rail is shown as a compact-screen drawer. */
  onRequestClose?: () => void
}

/**
 * The single Chat surface (docs/05 §3, design.md §2): the Chat view body and
 * the right rail are the same component, so exactly one conversation is ever
 * rendered and no second session is created.
 *
 * Message delivery is owned by LG-007 and is not implemented yet, so sending
 * never fabricates a message: it keeps the local draft and shows a notice.
 */
export function ChatPanel({ variant, onRequestClose }: ChatPanelProps) {
  const { state, dispatch } = useShell()
  const backend = useBackendStatus()
  const [notice, setNotice] = useState<string | null>(null)

  const key = draftKey(state.taskRef)
  const draft = state.drafts[key] ?? ''
  const scopeLabel = state.taskRef ?? 'Global'
  const messages = state.showLayoutMock ? MOCK_MESSAGES : []

  const backendLabel =
    backend.state === 'connected'
      ? 'connected'
      : backend.state === 'loading'
        ? 'checking…'
        : 'not connected'

  const handleSubmit = () => {
    if (!draft.trim()) return
    setNotice(
      'Not sent: message delivery is not implemented yet (LG-007/LG-013). Your draft is kept locally.',
    )
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
            Scope: {scopeLabel} · backend: {backendLabel}
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

      <div className="lg-chat__messages" aria-label="Conversation messages">
        {state.showLayoutMock ? (
          <p className="lg-mock-badge" role="note">
            {MOCK_NOTICE}
          </p>
        ) : null}
        {backend.state === 'unavailable' ? (
          <ErrorState
            title="Backend not connected"
            message={
              backend.error?.message ??
              'The local API is unreachable. Start it with `make run`.'
            }
            code={backend.error?.code}
            retryable={backend.error?.retryable ?? true}
            requestId={backend.error?.requestId}
            onRetry={backend.refresh}
          />
        ) : null}
        {messages.length === 0 && backend.state !== 'unavailable' ? (
          <EmptyState title="No messages yet">
            {backend.state === 'loading'
              ? 'Checking the local backend…'
              : 'Message delivery is not implemented yet (LG-007/LG-013).'}
          </EmptyState>
        ) : null}
        {messages.map((message) => (
          <article
            key={message.id}
            className={`lg-message lg-message--${message.role}`}
            data-mock="true"
          >
            <div className="lg-message__meta">
              <span>{message.role === 'user' ? 'You' : 'Bot'}</span>
              <span>{message.at}</span>
              <MockBadge />
            </div>
            <div className="lg-message__bubble">{message.content}</div>
          </article>
        ))}
      </div>

      <footer className="lg-chat__footer">
        {notice ? (
          <p className="lg-notice" role="status">
            {notice}
          </p>
        ) : null}
        <ChatComposer
          value={draft}
          onChange={(value) => {
            dispatch({ type: 'setDraft', key, value })
            if (notice) setNotice(null)
          }}
          onSubmit={handleSubmit}
          scopeLabel={scopeLabel}
        />
      </footer>
    </section>
  )
}
