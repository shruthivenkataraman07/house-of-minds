import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from '../App'

describe('environment smoke test', () => {
  it('renders the root component', () => {
    render(<App />)
    expect(screen.getAllByRole('button').length).toBeGreaterThan(0)
  })
})
