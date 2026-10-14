import { ChatPanel } from '../components/ChatPanel'

/**
 * Chat view body (owner view task: LG-013). LG-011 provides the shell wiring
 * and the single shared ChatPanel; message routing/delivery is LG-007/LG-013.
 */
export function ChatView() {
  return <ChatPanel variant="main" />
}
