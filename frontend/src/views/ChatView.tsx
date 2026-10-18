import { ChatBody } from './chat/ChatBody'

/**
 * Chat view body (owner: LG-013). Thin re-export: the real conversation surface
 * (global/Task history, attachments, drafts, message send) lives under
 * `views/chat/**` and is shared with the shell's right rail via ChatPanel.
 */
export function ChatView() {
  return <ChatBody variant="main" />
}
