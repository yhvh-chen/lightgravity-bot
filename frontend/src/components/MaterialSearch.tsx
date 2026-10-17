import { useEffect, useMemo, useRef, useState } from 'react'

import { createSourcesApi } from '../api/sources'
import { useShell } from '../app/ShellProvider'
import { ChatSourceSearch } from '../views/chat/ChatSourceSearch'
import { useMaterialSearch } from './useMaterialSearch'

/**
 * One always-visible material search input in the top bar. The input owns the
 * query; the panel reuses the real `/search` result view with the current Task
 * plus shared-material scope and the existing stale/empty/error states.
 */
export function MaterialSearch() {
  const { state, dispatch } = useShell()
  const api = useMemo(() => createSourcesApi(), [])
  const search = useMaterialSearch(api, state.taskRef)
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

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
      event.preventDefault()
      setOpen(false)
      inputRef.current?.focus()
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('keydown', escape)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('keydown', escape)
    }
  }, [open])

  const submit = () => {
    if (!search.draft.trim()) {
      inputRef.current?.focus()
      return
    }
    setOpen(true)
    search.run()
  }

  return (
    <div className="lg-top-search" ref={rootRef}>
      <input
        ref={inputRef}
        type="search"
        className="lg-input lg-top-search__input"
        placeholder="Search"
        aria-label="Search"
        aria-expanded={open}
        aria-controls={open ? 'lg-material-search' : undefined}
        autoComplete="off"
        enterKeyHint="search"
        value={search.draft}
        onChange={(event) => search.setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault()
            submit()
          }
          if (event.key === 'Escape') {
            // Keep the query; type=search would otherwise clear it natively.
            event.preventDefault()
            setOpen(false)
          }
        }}
      />
      {open ? (
        <section id="lg-material-search" className="lg-top-search__panel" aria-label="Search materials panel">
          <p className="lg-field__hint">{state.taskRef ? 'Current task and shared materials' : 'Shared materials'} · Text search</p>
          <ChatSourceSearch
            api={api}
            taskRef={state.taskRef}
            controller={search}
            showInput={false}
            onOpen={(sourceId) => {
              dispatch({ type: 'selectItem', itemRef: `source:${sourceId}` })
              dispatch({ type: 'setView', view: 'files' })
              setOpen(false)
            }}
          />
          <button
            type="button"
            className="lg-button"
            onClick={() => {
              setOpen(false)
              inputRef.current?.focus()
            }}
          >
            Close search
          </button>
        </section>
      ) : null}
    </div>
  )
}
