import { PlaceholderView } from './PlaceholderView'

/**
 * Resources view (owner: LG-015). Seven vertical categories are fixed by
 * docs/05 §6.1; the shell only renders the category navigation.
 */
export function ResourcesView() {
  return (
    <PlaceholderView
      viewId="resources"
      ownerTask="LG-015"
      title="Resources"
      summary="Connections, Session Profiles, Hooks, MCP, Tools, Triggers and Skills detail is not implemented in the shell."
      planned={[
        'Category detail with frontmatter fields, body, references and diagnostics',
        'Declared / parsed / dependency / runtime availability kept separate',
        'Navigation to the referencing template or member',
      ]}
    />
  )
}
