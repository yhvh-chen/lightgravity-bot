import { ChatBody } from '../views/chat/ChatBody'

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
 * As of LG-013 this delegates to the real conversation body
 * (`views/chat/ChatBody`): it reads global/Task history from the backend and
 * sends through the frozen endpoints, keeping the draft on failure instead of
 * fabricating a message.
 */
export function ChatPanel({ variant, onRequestClose }: ChatPanelProps) {
  return <ChatBody variant={variant} onRequestClose={onRequestClose} />
}
