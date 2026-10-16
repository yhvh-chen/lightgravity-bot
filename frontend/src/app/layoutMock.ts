/**
 * Clearly-labelled layout mock (LG-011).
 *
 * design.md §8 forbids mock screenshots pretending to be real state and
 * §4 forbids hard-coding backend facts. The shell therefore ships *no*
 * business data by default except this explicitly labelled mock, which exists
 * only to exercise the multi-column layout (context rail, cards, status
 * badges, chat messages). Every surface rendering it shows `MOCK_NOTICE`, and
 * the top bar toggle turns it off to reveal the real empty/not-connected
 * states. Owning view tasks (LG-013/014/015/026) replace these with API data.
 */
import type { StatusKind } from '../components/StatusBadge'

export const MOCK_NOTICE = 'MOCK LAYOUT DATA — not from backend'

export interface MockTask {
  mock: true
  id: string
  title: string
  phase: string
  status: 'todo' | 'in-progress' | 'done'
  statusKind: StatusKind
  runRef: string | null
}

export const MOCK_TASKS: readonly MockTask[] = [
  {
    mock: true,
    id: 'mock-task-1',
    title: 'Add login to the example site',
    phase: 'executing',
    status: 'in-progress',
    statusKind: 'accent',
    runRef: 'mock-run-1',
  },
  {
    mock: true,
    id: 'mock-task-2',
    title: 'Write CSV export test',
    phase: 'awaiting_acceptance',
    status: 'in-progress',
    statusKind: 'warning',
    runRef: 'mock-run-2',
  },
  {
    mock: true,
    id: 'mock-task-3',
    title: 'Fix flaky scheduler test',
    phase: 'failed',
    status: 'in-progress',
    statusKind: 'error',
    runRef: 'mock-run-3',
  },
  {
    mock: true,
    id: 'mock-task-4',
    title: 'Document navigation contract',
    phase: 'completed',
    status: 'done',
    statusKind: 'success',
    runRef: null,
  },
] as const

export interface MockNotification {
  mock: true
  id: string
  title: string
  at: string
}

export const MOCK_NOTIFICATIONS: readonly MockNotification[] = [
  {
    mock: true,
    id: 'mock-notif-1',
    title: 'Task needs your decision (mock)',
    at: '2026-10-15T00:00:00Z',
  },
  {
    mock: true,
    id: 'mock-notif-2',
    title: 'Candidate delivery ready (mock)',
    at: '2026-10-15T00:05:00Z',
  },
] as const

export const MOCK_RUNS_BY_TASK: Record<string, readonly string[]> = {
  'mock-task-1': ['mock-run-1'],
  'mock-task-2': ['mock-run-2'],
  'mock-task-3': ['mock-run-3'],
}

export interface MockResource {
  mock: true
  id: string
  label: string
  meta: string
}

export const MOCK_AVAILABLE_ROLES: readonly MockResource[] = [
  { mock: true, id: 'mock-role-developer', label: 'Developer', meta: 'template · declared only' },
  { mock: true, id: 'mock-role-verifier', label: 'Verifier', meta: 'template · declared only' },
] as const

export const MOCK_RECRUITED_MEMBERS: readonly MockResource[] = [
  { mock: true, id: 'mock-member-1', label: 'Developer (task 1)', meta: 'running · mock-run-1' },
  { mock: true, id: 'mock-member-2', label: 'Verifier (task 1)', meta: 'ready · mock-run-1' },
] as const

export interface MockMessage {
  mock: true
  id: string
  role: 'user' | 'assistant'
  content: string
  at: string
}

export const MOCK_MESSAGES: readonly MockMessage[] = [
  {
    mock: true,
    id: 'mock-msg-1',
    role: 'user',
    content: 'Add a login page to the example site.',
    at: '2026-10-15T00:00:00Z',
  },
  {
    mock: true,
    id: 'mock-msg-2',
    role: 'assistant',
    content:
      'Layout mock only — no execution backend is connected yet (LG-007/LG-013).',
    at: '2026-10-15T00:01:00Z',
  },
] as const
