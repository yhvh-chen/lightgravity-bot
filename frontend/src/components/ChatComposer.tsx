import { useRef, type ChangeEvent, type KeyboardEvent } from 'react'

export interface ChatComposerProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  /** Scope the draft belongs to, e.g. "Global" or "task_...". */
  scopeLabel: string
  /** Optional extra hint (e.g. team @bot usage). Defaults to the send hint. */
  hint?: string
  disabled?: boolean
  disabledReason?: string
}

/**
 * Shared ChatComposer (design.md §5 Chat). The draft is owned by shell state,
 * so switching views keeps the text. Enter sends, Shift+Enter adds a newline,
 * and IME composition never triggers a send.
 */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  scopeLabel,
  hint,
  disabled = false,
  disabledReason,
}: ChatComposerProps) {
  const composing = useRef(false)

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    onChange(event.target.value)
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter') return
    if (event.shiftKey) return
    if (composing.current || event.nativeEvent.isComposing) return
    event.preventDefault()
    onSubmit()
  }

  return (
    <div className="lg-composer">
      <label className="lg-visually-hidden" htmlFor="lg-chat-input">
        Message for {scopeLabel}
      </label>
      <textarea
        id="lg-chat-input"
        className="lg-composer__input"
        value={value}
        placeholder="Message…"
        disabled={disabled}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => {
          composing.current = true
        }}
        onCompositionEnd={() => {
          composing.current = false
        }}
      />
      <div className="lg-composer__row">
        <span className="lg-composer__hint">
          {hint ?? 'Enter to send · Shift+Enter for a new line'}
        </span>
        <button
          type="button"
          className="lg-button lg-button--primary"
          onClick={onSubmit}
          disabled={disabled}
          title={disabled ? disabledReason : undefined}
        >
          Send
        </button>
      </div>
    </div>
  )
}
