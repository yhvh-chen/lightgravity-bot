import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DetailHeader } from '../src/components/DetailHeader'
import { EmptyState } from '../src/components/EmptyState'
import { ErrorState } from '../src/components/ErrorState'
import { MarkdownViewer } from '../src/components/MarkdownViewer'
import { ResourceCard } from '../src/components/ResourceCard'
import { StatusBadge } from '../src/components/StatusBadge'
import { TaskCard } from '../src/components/TaskCard'

/**
 * Shared component layer smoke checks (LG-011, design.md §4). These components
 * are the reusable primitives view tasks build on.
 */
describe('shared component layer', () => {
  it('TaskCard shows phase, status and a mock marker', () => {
    render(
      <TaskCard
        title="Add login"
        phase="executing"
        statusLabel="in-progress"
        statusKind="accent"
        taskRef="task_1"
        runRef="run_1"
        mock
      />,
    )
    expect(screen.getByRole('heading', { name: 'Add login' })).toBeInTheDocument()
    expect(screen.getByText('phase: executing')).toBeInTheDocument()
    expect(screen.getByText('in-progress')).toBeInTheDocument()
    expect(screen.getByText('mock')).toBeInTheDocument()
  })

  it('ResourceCard separates kind and declared availability', () => {
    render(
      <ResourceCard
        title="antigravity-primary"
        kind="connection"
        path="resources/connections/antigravity-primary.md"
        availability={{ kind: 'warning', label: 'declared only' }}
      />,
    )
    expect(screen.getByText('kind: connection')).toBeInTheDocument()
    expect(screen.getByText('declared only')).toBeInTheDocument()
  })

  it('DetailHeader renders meta key/value pairs', () => {
    render(
      <DetailHeader
        title="Files"
        meta={[
          { label: 'view', value: 'files' },
          { label: 'owner', value: 'LG-014' },
        ]}
      />,
    )
    expect(screen.getByRole('heading', { name: 'Files' })).toBeInTheDocument()
    expect(screen.getByText('LG-014')).toBeInTheDocument()
  })

  it('status badges carry text, not color alone', () => {
    render(<StatusBadge kind="error">failed</StatusBadge>)
    expect(screen.getByText('failed')).toHaveClass('lg-status-badge--error')
  })

  it('EmptyState and ErrorState expose role=status/alert', () => {
    render(
      <>
        <EmptyState title="Nothing here">Next step.</EmptyState>
        <ErrorState title="Boom" message="failed" code="internal_error" />
      </>,
    )
    expect(screen.getByRole('status')).toHaveTextContent('Nothing here')
    expect(screen.getByRole('alert')).toHaveTextContent('internal_error')
  })

  it('MarkdownViewer renders text without executing HTML', () => {
    render(<MarkdownViewer content={'# Title\n\n- one\n<script>alert(1)</script>'} />)
    expect(screen.getByRole('heading', { name: 'Title' })).toBeInTheDocument()
    expect(screen.getByText('one')).toBeInTheDocument()
    expect(screen.getByText('<script>alert(1)</script>')).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
  })
})
