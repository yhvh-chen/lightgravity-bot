import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'

import {
  createHistoryApi,
  type ConversationHistoryItem,
  type HistoryApi,
} from '../../api/history'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Icon } from '../../components/icons'

import './history.css'

export interface ChatHistoryProps {
  /** Team mode is enabled; the icon is never shown in single-user mode. */
  isTeam: boolean
  /**
   * Active Chat channel when known.  Team mode with `personal` selected hides
   * the history icon (the list is a shared Team surface only).
   */
  channel?: 'personal' | 'team' | null
  /** Current Task scope; `null` means the General/global conversation. */
  activeTaskRef?: string | null
  /**
   * Select an existing Task conversation (or General with `null`).
   * The parent must change the normal Task scope; this component never creates
   * a Task, Run or new conversation/session.
   */
  onSelectTask: (taskRef: string | null) => void
  /** Injectable for tests; defaults to `GET /conversations/history`. */
  api?: HistoryApi
}

/**
 * LG-205 Team conversation history.
 *
 * Opens a bounded list of General and Tasks that have a persisted message,
 * ordered by the backend using the **actual last-message timestamp**.  It does
 * not fetch each Task separately and does not derive recency from Task
 * metadata.  The parent owns navigation so selecting an entry is exactly the
 * existing Task-scope switch.
 */
export function ChatHistory(props: ChatHistoryProps) {
  if (!props.isTeam || props.channel === 'personal') return null
  return <TeamChatHistory {...props} />
}

function TeamChatHistory({ activeTaskRef = null, onSelectTask, api: injectedApi }: ChatHistoryProps) {
  const api = useMemo(() => injectedApi ?? createHistoryApi(), [injectedApi])
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<ConversationHistoryItem[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dialogId = useId()
  const rootRef = useRef<HTMLDivElement | null>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const popoverRef = useRef<HTMLDivElement | null>(null)
  const request = useRef<AbortController | null>(null)

  const close = useCallback((restoreFocus: boolean) => {
    request.current?.abort()
    request.current = null
    setOpen(false)
    setLoading(false)
    if (restoreFocus) {
      requestAnimationFrame(() => triggerRef.current?.focus())
    }
  }, [])

  const load = useCallback(() => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    setItems(null)
    setError(null)
    setLoading(true)
    api.listHistory(controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return
        setItems(page.items)
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return
        setError(cause instanceof Error ? cause.message : 'Could not load conversation history')
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
  }, [api])

  useEffect(() => () => request.current?.abort(), [])

  useEffect(() => {
    if (!open) return
    const frame = requestAnimationFrame(() => popoverRef.current?.focus())
    return () => cancelAnimationFrame(frame)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (rootRef.current?.contains(target)) return
      close(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open, close])

  const toggle = () => {
    if (open) {
      close(true)
      return
    }
    setOpen(true)
    load()
  }

  const select = (item: ConversationHistoryItem) => {
    close(false)
    onSelectTask(item.task_ref)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape' && open) {
      event.preventDefault()
      event.stopPropagation()
      close(true)
      return
    }
    if (!open) return
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return
    const buttons = Array.from(
      popoverRef.current?.querySelectorAll<HTMLButtonElement>('[data-history-item]') ?? [],
    )
    if (buttons.length === 0) return
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement)
    let next = current
    if (event.key === 'ArrowDown') next = current < 0 ? 0 : Math.min(current + 1, buttons.length - 1)
    if (event.key === 'ArrowUp') next = current < 0 ? buttons.length - 1 : Math.max(current - 1, 0)
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = buttons.length - 1
    event.preventDefault()
    buttons[next]?.focus()
  }

  return (
    <div className="lg-chat-history" ref={rootRef} onKeyDown={handleKeyDown}>
      <button
        ref={triggerRef}
        type="button"
        className="lg-icon-button"
        aria-label="Conversation history"
        title="Conversation history"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? dialogId : undefined}
        onClick={toggle}
      >
        <Icon name="history" />
      </button>
      {open ? (
        <div
          id={dialogId}
          ref={popoverRef}
          className="lg-chat-history__popover"
          role="dialog"
          aria-label="Conversation history"
          tabIndex={-1}
        >
          <div className="lg-chat-history__head">
            <p className="lg-chat-history__title">Team conversations</p>
            <p className="lg-chat-history__hint">Most recent message first</p>
          </div>
          {loading ? <p className="lg-chat-history__status" role="status">Loading conversation history…</p> : null}
          {error ? (
            <ErrorState
              title="History unavailable"
              message={error}
              retryable
              onRetry={load}
            />
          ) : null}
          {!loading && !error && items?.length === 0 ? (
            <EmptyState title="No conversations yet" compact>
              Send a message in Team to start a conversation.
            </EmptyState>
          ) : null}
          {!loading && !error && items && items.length > 0 ? (
            <ul className="lg-chat-history__list" aria-label="Team conversation history">
              {items.map((item) => {
                const active = item.kind === 'general'
                  ? activeTaskRef === null
                  : activeTaskRef === item.task_ref
                const at = formatHistoryTime(item.last_message_at)
                return (
                  <li key={item.kind === 'general' ? 'general' : item.task_ref}>
                    <button
                      type="button"
                      className="lg-chat-history__item"
                      data-history-item
                      aria-current={active ? 'page' : undefined}
                      title={item.task_ref ?? 'Global conversation without a Task scope'}
                      onClick={() => select(item)}
                    >
                      <span className="lg-chat-history__item-title">{item.title}</span>
                      {at ? <time className="lg-chat-history__time" dateTime={item.last_message_at ?? undefined}>{at}</time> : null}
                    </button>
                  </li>
                )
              })}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function formatHistoryTime(value: string | null): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
