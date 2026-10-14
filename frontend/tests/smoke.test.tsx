import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { App } from '../src/App'

describe('App shell skeleton', () => {
  it('renders the product name', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: 'LightGravity Bot' }),
    ).toBeInTheDocument()
  })
})
