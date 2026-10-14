import { PlaceholderView } from './PlaceholderView'

/**
 * Team view (owner: LG-015). Available = agent templates, Recruited = live
 * Task/Run Member instances (docs/05 §5).
 */
export function TeamView() {
  return (
    <PlaceholderView
      viewId="team"
      ownerTask="LG-015"
      title="Team"
      summary="Available role templates and Recruited member instances are not implemented in the shell."
      planned={[
        'Available: resources/agents templates with declared vs actual availability',
        'Recruited: Member instances for the active Task/Run, excluding released',
        'Resource reference navigation back to the originating member',
      ]}
    />
  )
}
