import {
  useCallback,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'

export interface PanelResizerProps {
  /** Accessible name, e.g. "Resize context panel". */
  label: string
  /** Which side the panel being resized sits on. */
  side: 'left' | 'right'
  value: number
  min: number
  max: number
  step?: number
  onChange: (value: number) => void
}

/**
 * Shared SplitPane divider (design.md §4, §7). Draggable with the pointer and
 * fully keyboard operable so column widths never require a mouse.
 */
export function PanelResizer({
  label,
  side,
  value,
  min,
  max,
  step = 16,
  onChange,
}: PanelResizerProps) {
  const drag = useRef<{ startX: number; startValue: number } | null>(null)

  const apply = useCallback(
    (next: number) => {
      onChange(Math.min(max, Math.max(min, Math.round(next))))
    },
    [max, min, onChange],
  )

  const onPointerDown = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault()
      drag.current = { startX: event.clientX, startValue: value }
      const target = event.currentTarget
      target.setPointerCapture?.(event.pointerId)

      const move = (moveEvent: PointerEvent) => {
        const state = drag.current
        if (!state) return
        const delta = moveEvent.clientX - state.startX
        apply(state.startValue + (side === 'left' ? delta : -delta))
      }
      const up = () => {
        drag.current = null
        window.removeEventListener('pointermove', move)
        window.removeEventListener('pointerup', up)
      }
      window.addEventListener('pointermove', move)
      window.addEventListener('pointerup', up)
    },
    [apply, side, value],
  )

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      const grow = side === 'left' ? 'ArrowRight' : 'ArrowLeft'
      const shrink = side === 'left' ? 'ArrowLeft' : 'ArrowRight'
      switch (event.key) {
        case grow:
          event.preventDefault()
          apply(value + step)
          break
        case shrink:
          event.preventDefault()
          apply(value - step)
          break
        case 'Home':
          event.preventDefault()
          apply(min)
          break
        case 'End':
          event.preventDefault()
          apply(max)
          break
        default:
          break
      }
    },
    [apply, max, min, side, step, value],
  )

  return (
    <div
      className="lg-resizer"
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
    />
  )
}
