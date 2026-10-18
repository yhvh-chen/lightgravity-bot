import type { ComponentType } from 'react'
import type { ViewId } from '../app/navigation'
import { useShell } from '../app/ShellProvider'
import { connectionIdFromRef } from '../app/uiState'
import { BoardView } from './BoardView'
import { FilesView } from './files/FilesView'
import { ResourcesView } from './ResourcesView'
import { SettingsView } from './settings/SettingsView'
import { TeamView } from './TeamView'

function SettingsRoute() {
  const { state } = useShell()
  return <SettingsView connectionId={connectionIdFromRef(state.selectedItemRef)} taskRef={state.taskRef} />
}

/** Each view owns its content; the shell has one navigation and no context rail. */
export const VIEW_DEFINITIONS: Record<ViewId, { Main: ComponentType }> = {
  tasks: { Main: FilesView }, board: { Main: BoardView },
  team: { Main: TeamView }, resources: { Main: ResourcesView }, settings: { Main: SettingsRoute },
}
