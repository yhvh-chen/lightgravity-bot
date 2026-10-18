/** Availability facts from health; a missing capability never means ready. */
export function ExecutionAvailability({ available, checked = true }: { available: boolean | null; checked?: boolean }) {
  if (!checked || available === true) return null
  return <p className="lg-notice" role="status">
    {available === false
      ? 'Execution unavailable. Task execution is disabled on this server.'
      : 'Execution status unknown. This server has not confirmed Task execution availability.'}
  </p>
}
