import type { ViewId } from '../app/navigation'
import { DetailHeader } from '../components/DetailHeader'
import { EmptyState } from '../components/EmptyState'
import { StatusBadge } from '../components/StatusBadge'

export interface PlaceholderViewProps {
  viewId: ViewId
  ownerTask: string
  title: string
  summary: string
  planned: readonly string[]
}

/**
 * Independent view entry point (LG-011).
 *
 * The shell owns layout/navigation only; each business view is implemented by
 * its own task (LG-013/014/015/026) inside `src/views/`. Until then this
 * placeholder states exactly what is missing instead of showing fake data.
 */
export function PlaceholderView({
  viewId,
  ownerTask,
  title,
  summary,
  planned,
}: PlaceholderViewProps) {
  return (
    <div>
      <DetailHeader
        title={title}
        badges={<StatusBadge kind="warning">Not implemented ({ownerTask})</StatusBadge>}
        meta={[
          { label: 'view', value: viewId },
          { label: 'owner', value: ownerTask },
        ]}
      />
      <EmptyState title="This view is not implemented yet">
        <p>{summary}</p>
        <p>
          LG-011 provides the shell mount point only. No business API is connected
          and no task/team/file data is shown here yet.
        </p>
        <ul>
          {planned.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </EmptyState>
    </div>
  )
}
