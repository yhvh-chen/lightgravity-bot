import type { ComponentType } from 'react'

import { MOCK_TASKS } from '../app/layoutMock'
import type { ViewId } from '../app/navigation'
import { useShell } from '../app/ShellProvider'
import { parseSettingsConnectionRef } from '../app/uiState'
import type { ShellState } from '../app/uiState'
import type { ContextItem, ContextSection } from '../components/ContextList'
import { BoardView } from './BoardView'
import { ChatView } from './ChatView'
import { FilesView } from './files/FilesView'
import { ResourcesView } from './ResourcesView'
import { ResourcesContextRail } from './resources/contextRail'
import { SettingsView } from './settings/SettingsView'
import { TeamView } from './TeamView'
import { TeamContextRail } from './team/contextRail'

export interface ViewContextProps {
  selectedId: string | null
  onSelect: (item: ContextItem) => void
}

export interface ViewDefinition {
  id: ViewId
  /** Title shown at the top of the context rail. */
  contextTitle: string
  contextAriaLabel: string
  Main: ComponentType
  /** Context rail content. Sections explain their own empty state. */
  buildContext: (state: ShellState) => ContextSection[]
  /**
   * Optional data-driven context rail.  When present it replaces the static
   * `buildContext` sections, so the shell can show real backend data instead of
   * a labelled mock.
   */
  Context?: ComponentType<ViewContextProps>
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

/** Settings main panel with the selected Connection record located by id. */
function SettingsRoute() {
  const { state } = useShell()
  return (
    <SettingsView
      connectionId={parseSettingsConnectionRef(state.selectedItemRef)}
      taskRef={state.taskRef}
    />
  )
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
          ? 'File tree is loaded in the main panel for this Task scope.'
          : 'Select a Task scope to browse its files.',
      },
    ],
  },
  team: {
    id: 'team',
    contextTitle: 'Team',
    contextAriaLabel: 'Team recruitment',
    Main: TeamView,
    Context: TeamContextRail,
    buildContext: () => [
      {
        id: 'team-available',
        title: 'Available',
        items: [],
        empty: 'Available role templates load from the backend rail.',
      },
      {
        id: 'team-recruited',
        title: 'Recruited',
        items: [],
        empty: 'Recruited members load from the backend rail.',
      },
    ],
  },
  resources: {
    id: 'resources',
    contextTitle: 'Resources',
    contextAriaLabel: 'Resource categories',
    Main: ResourcesView,
    Context: ResourcesContextRail,
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
    Main: SettingsRoute,
    buildContext: () => [
      {
        id: 'models-providers',
        title: 'Models & Providers',
        items: [],
        empty: 'Models & Providers is shown in the main panel.',
      },
    ],
  },
}
