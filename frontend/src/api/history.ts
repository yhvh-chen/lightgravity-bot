/**
 * Read-only Team conversation history (LG-205).
 *
 * `GET /conversations/history` is one bounded projection over the same
 * persisted global/Task message logs the Chat readers use.  The server returns
 * the **actual last persisted message** timestamp per Task; the browser must
 * not substitute `TASK.md`/directory activity or fetch every Task separately.
 */

import { apiRequest } from './client'

export type ConversationHistoryKind = 'general' | 'task'

export interface ConversationHistoryItem {
  kind: ConversationHistoryKind
  /** `null` only for the fixed General/global entry. */
  task_ref: string | null
  title: string
  /** Exact persisted message `at`; `null` only when no message has a timestamp. */
  last_message_at: string | null
  last_message_seq: number | null
}

export interface ConversationHistoryPage {
  items: ConversationHistoryItem[]
}

export interface HistoryApi {
  listHistory(signal?: AbortSignal): Promise<ConversationHistoryPage>
}

export function createHistoryApi(): HistoryApi {
  return {
    listHistory(signal) {
      return apiRequest<ConversationHistoryPage>('/conversations/history', { signal })
    },
  }
}

export const historyApi: HistoryApi = createHistoryApi()
