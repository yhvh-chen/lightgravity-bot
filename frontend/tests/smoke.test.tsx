import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from '../src/App'

describe('App shell skeleton', () => {
  it('renders the product name', async () => {
    render(<App />)
    // The shell mounts after the async `/auth/me` probe; never assume it
    // synchronously to bypass the login gate.
    expect(
      await screen.findByRole('heading', { name: 'LightGravity Bot' }),
    ).toBeInTheDocument()
  })
})
