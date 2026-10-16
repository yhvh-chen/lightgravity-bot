import { Fragment, type ReactNode } from 'react'

/**
 * Minimal, rendering-only Markdown view (design.md §4, §5 Files).
 *
 * It intentionally supports a tiny subset (headings, unordered lists, blank
 * line separated paragraphs) using React elements only — no
 * `dangerouslySetInnerHTML`, no raw HTML, no script or link execution. A
 * richer renderer can replace it inside a view task without touching the
 * shell.
 */
export function MarkdownViewer({ content }: { content: string }) {
  return (
    <div className="lg-markdown" data-testid="markdown-viewer">
      {renderBlocks(content)}
    </div>
  )
}

function renderBlocks(content: string): ReactNode {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let listBuffer: string[] = []

  const flushList = (key: string) => {
    if (listBuffer.length === 0) return
    blocks.push(
      <ul key={key}>
        {listBuffer.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>,
    )
    listBuffer = []
  }

  lines.forEach((rawLine, index) => {
    const line = rawLine.trimEnd()
    if (line.startsWith('- ')) {
      listBuffer.push(line.slice(2))
      return
    }
    flushList(`list-${index}`)
    if (line.trim() === '') return
    if (line.startsWith('###### ')) {
      blocks.push(<h6 key={index}>{line.slice(7)}</h6>)
    } else if (line.startsWith('##### ')) {
      blocks.push(<h5 key={index}>{line.slice(6)}</h5>)
    } else if (line.startsWith('#### ')) {
      blocks.push(<h4 key={index}>{line.slice(5)}</h4>)
    } else if (line.startsWith('### ')) {
      blocks.push(<h3 key={index}>{line.slice(4)}</h3>)
    } else if (line.startsWith('## ')) {
      blocks.push(<h2 key={index}>{line.slice(3)}</h2>)
    } else if (line.startsWith('# ')) {
      blocks.push(<h1 key={index}>{line.slice(2)}</h1>)
    } else if (line.startsWith('```')) {
      // Code fences are rendered as plain monospace text, never executed.
      blocks.push(
        <pre key={index}>
          <code>{line.slice(3)}</code>
        </pre>,
      )
    } else {
      blocks.push(<p key={index}>{line}</p>)
    }
  })
  flushList('list-final')

  return (
    <>
      {blocks.map((block, index) => (
        <Fragment key={index}>{block}</Fragment>
      ))}
    </>
  )
}
