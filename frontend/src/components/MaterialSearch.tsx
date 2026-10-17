import { useEffect, useMemo, useRef, useState } from 'react'
import { createSourcesApi } from '../api/sources'
import { useShell } from '../app/ShellProvider'
import { ChatSourceSearch } from '../views/chat/ChatSourceSearch'

/** One real material search entry, shared by all pages. */
export function MaterialSearch() {
  const { state, dispatch } = useShell()
  const api = useMemo(() => createSourcesApi(), [])
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  // Search is a transient overlay. Navigation must reveal the destination's
  // controls, even when activated by keyboard without a pointer event.
  useEffect(() => { setOpen(false) }, [state.view, state.taskRef, state.selectedItemRef])
  useEffect(() => {
    if (!open) return
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false)
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setOpen(false)
      triggerRef.current?.focus()
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('keydown', escape)
    }
  }, [open])
  return (
    <div className="lg-top-search" ref={rootRef}>
      <button ref={triggerRef} type="button" className="lg-button" aria-expanded={open} aria-controls="lg-material-search" onClick={() => setOpen(!open)}>
        Search materials
      </button>
      {open ? (
        <section id="lg-material-search" className="lg-top-search__panel" aria-label="Search materials panel">
          <p className="lg-field__hint">{state.taskRef ? 'Current task and shared materials' : 'Shared materials'} · Text search</p>
          <ChatSourceSearch api={api} taskRef={state.taskRef} onOpen={(sourceId) => {
            dispatch({ type: 'selectItem', itemRef: `source:${sourceId}` })
            dispatch({ type: 'setView', view: 'files' })
            setOpen(false)
          }} />
          <button type="button" className="lg-button" onClick={() => setOpen(false)}>Close search</button>
        </section>
      ) : null}
    </div>
  )
}
