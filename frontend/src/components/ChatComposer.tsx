import {
  useEffect,
  useRef,
  type ChangeEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'

import { Icon } from './icons'

export interface ChatComposerProps {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  /** Scope the draft belongs to, e.g. "Global" or "task_...". */
  scopeLabel: string
  disabled?: boolean
  disabledReason?: string
  /**
   * LG-119: direct native file picker.  The button is inside the composer at
   * bottom-left; clicking it opens the OS picker immediately (no menu).  A
   * cancelled picker produces an empty list and therefore no request.
   */
  onFilesPicked?: (files: File[]) => void
  attachDisabled?: boolean
  attachDisabledReason?: string
  /** Pending attachment chips shown above the input; may wrap to multiple rows. */
  attachments?: ReactNode
}

/**
 * Shared ChatComposer (design.md §5 Chat). The draft is owned by shell state,
 * so switching views keeps the text. Enter sends, Shift+Enter adds a newline,
 * and IME composition never triggers a send.
 *
 * The textarea grows upward with its content and scrolls internally after
 * min(240px, 35dvh). No permanent bottom instruction line or top divider is
 * rendered; the only controls are the file picker and the send icon.
 */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  scopeLabel,
  disabled = false,
  disabledReason,
  onFilesPicked,
  attachDisabled = false,
  attachDisabledReason,
  attachments,
}: ChatComposerProps) {
  const composing = useRef(false)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    const viewport = typeof window === 'undefined' ? 800 : window.innerHeight
    const max = Math.min(240, Math.max(80, viewport * 0.35))
    input.style.height = 'auto'
    const next = Math.min(input.scrollHeight, max)
    input.style.height = `${next}px`
    input.style.overflowY = input.scrollHeight > max ? 'auto' : 'hidden'
  }, [value])

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

  const handlePick = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files ? Array.from(event.target.files) : []
    // Resetting the value lets the same file be picked again after a failure.
    event.target.value = ''
    if (files.length === 0) return
    onFilesPicked?.(files)
  }

  const attachDisabledNow = disabled || attachDisabled || !onFilesPicked
  const attachTitle = attachDisabledNow
    ? attachDisabledReason ?? disabledReason ?? 'File upload is unavailable'
    : 'Upload file'
  const sendTitle = disabled ? disabledReason ?? 'Message is being sent…' : 'Send'

  return (
    <div className="lg-composer">
      <label className="lg-visually-hidden" htmlFor="lg-chat-input">
        Message for {scopeLabel}
      </label>
      <input
        ref={fileRef}
        type="file"
        multiple
        className="lg-visually-hidden"
        aria-label={`Upload file for ${scopeLabel}`}
        onChange={handlePick}
        tabIndex={-1}
      />
      {attachments ? (
        <div className="lg-composer__attachments" aria-label="Attachments">
          {attachments}
        </div>
      ) : null}
      <div className="lg-composer__box">
        <textarea
          ref={inputRef}
          id="lg-chat-input"
          className="lg-composer__input"
          value={value}
          placeholder="Message…"
          rows={1}
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
        <div className="lg-composer__actions">
          <button
            type="button"
            className="lg-icon-button lg-composer__attach"
            onClick={() => fileRef.current?.click()}
            disabled={attachDisabledNow}
            title={attachTitle}
            aria-label="Upload file"
          >
            <Icon name="files" size={18} />
          </button>
          <button
            type="button"
            className="lg-icon-button lg-composer__send"
            onClick={onSubmit}
            disabled={disabled}
            title={sendTitle}
            aria-label="Send message"
          >
            <Icon name="send" size={18} />
          </button>
        </div>
      </div>
    </div>
  )
}
