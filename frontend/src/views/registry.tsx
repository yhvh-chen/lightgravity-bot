import type { ComponentType } from 'react'

import {
  MOCK_AVAILABLE_ROLES,
  MOCK_RECRUITED_MEMBERS,
  MOCK_TASKS,
} from '../app/layoutMock'
import type { ViewId } from '../app/navigation'
import type { ShellState } from '../app/uiState'
import type { ContextItem, ContextSection } from '../components/ContextList'
import { BoardView } from './BoardView'
import { ChatView } from './ChatView'
import { FilesView } from './FilesView'
import { ResourcesView } from './ResourcesView'
import { SettingsView } from './SettingsView'
import { TeamView } from './TeamView'

export interface ViewDefinition {
  id: ViewId
  /** Title shown at the top of the context rail. */
  contextTitle: string
  contextAriaLabel: string
  Main: ComponentType
  /** Context rail content. Sections explain their own empty state. */
  buildContext: (state: ShellState) => ContextSection[]
}

/** Frozen Resources categories (docs/05 §6.1) — shell navigation, not data. */
const RESOURCE_CATEGORIES: readonly ContextItem[] = [
  { id: 'connections', label: 'Connections' },
  { id: 'session-profiles', label: 'Session Profiles' },
  { id: 'hooks', label: 'Hooks' },
  { id: 'mcp', label: 'MCP' },
  { id: 'tools', label: 'Tools' },
  { id: 'triggers', label: 'Triggers' },
  { id: 'skills', label: 'Skills' },
]

function mockTaskItems(): ContextItem[] {
  return MOCK_TASKS.map((task) => ({
    id: task.id,
    label: task.title,
    meta: `phase: ${task.phase}`,
    status: { kind: task.statusKind, label: task.status },
    mock: true,
    taskRef: task.id,
  }))
}

export const VIEW_DEFINITIONS: Record<ViewId, ViewDefinition> = {
  chat: {
    id: 'chat',
    contextTitle: 'Conversations',
    contextAriaLabel: 'Conversation history',
    Main: ChatView,
    buildContext: (state) => [
      {
        id: 'chat-history',
        title: 'Task history',
        items: state.showLayoutMock ? mockTaskItems() : [],
        empty: 'No task history yet. Describe a goal in Chat to create one.',
      },
    ],
  },
  board: {
    id: 'board',
    contextTitle: 'Tasks',
    contextAriaLabel: 'Task scope',
    Main: BoardView,
    buildContext: (state) => [
      {
        id: 'board-tasks',
        title: 'Task scope',
        items: state.showLayoutMock ? mockTaskItems() : [],
        empty: 'No tasks yet — create one from Chat.',
      },
    ],
  },
  files: {
    id: 'files',
    contextTitle: 'Files',
    contextAriaLabel: 'Task files',
    Main: FilesView,
    buildContext: (state) => [
      {
        id: 'files',
        title: state.taskRef ? `Task ${state.taskRef}` : 'Workspace',
        items: [],
        empty: state.taskRef
          ? 'File tree is not loaded (LG-014).'
          : 'Select a Task scope to browse its files.',
      },
    ],
  },
  team: {
    id: 'team',
    contextTitle: 'Team',
    contextAriaLabel: 'Team recruitment',
    Main: TeamView,
    buildContext: (state) => [
      {
        id: 'team-available',
        title: 'Available',
        items: state.showLayoutMock
          ? MOCK_AVAILABLE_ROLES.map((role) => ({
              id: role.id,
              label: role.label,
              meta: role.meta,
              mock: true,
            }))
          : [],
        empty: 'No role templates loaded (LG-015).',
      },
      {
        id: 'team-recruited',
        title: 'Recruited',
        items: state.showLayoutMock
          ? MOCK_RECRUITED_MEMBERS.map((member) => ({
              id: member.id,
              label: member.label,
              meta: member.meta,
              mock: true,
            }))
          : [],
        empty: state.taskRef
          ? 'No members recruited for this Task.'
          : 'Select a Task to see its current team.',
      },
    ],
  },
  resources: {
    id: 'resources',
    contextTitle: 'Resources',
    contextAriaLabel: 'Resource categories',
    Main: ResourcesView,
    buildContext: () => [
      {
        id: 'resources-categories',
        title: 'Categories',
        items: RESOURCE_CATEGORIES,
        empty: 'No categories.',
      },
    ],
  },
  settings: {
    id: 'settings',
    contextTitle: 'Settings',
    contextAriaLabel: 'Settings sections',
    Main: SettingsView,
    buildContext: () => [
      {
        id: 'models-providers',
        title: 'Models & Providers',
        items: [],
        empty: 'Connection list is implemented by LG-026.',
      },
    ],
  },
}
