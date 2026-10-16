import { BoardBody } from './board/BoardBody'

/**
 * Board view (owner: LG-013; docs/08 §11).
 *
 * Thin re-export so the LG-011 registry keeps mounting `./BoardView` while the
 * real Task/Run board lives under `views/board/**`.
 */
export function BoardView() {
  return <BoardBody />
}
