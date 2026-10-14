import { PlaceholderView } from './PlaceholderView'

/**
 * Files view (owner: LG-014). Read-only workspace browsing/preview is wired by
 * LG-014 against the restricted `/api/v1/files` endpoints.
 */
export function FilesView() {
  return (
    <PlaceholderView
      viewId="files"
      ownerTask="LG-014"
      title="Files"
      summary="Workspace file tree and read-only preview are not implemented in the shell."
      planned={[
        'Restricted file tree from GET /api/v1/files',
        'Markdown/code/image preview (no script execution)',
        'Artifact and evidence association per task_ref',
      ]}
    />
  )
}
