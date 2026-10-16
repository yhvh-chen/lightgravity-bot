import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  type AccountApi,
  type AccountCreateInput,
  type AccountPasswordResetInput,
  type AccountUpdateInput,
  type AccountView,
  type OwnPasswordChangeInput,
} from '../src/api/accounts'
import { ApiError } from '../src/api/client'
import { supportsAccounts } from '../src/api/backendCompatibility'
import { AccountsPanel } from '../src/views/settings/AccountsPanel'
import { MyAccountPanel } from '../src/views/settings/MyAccountPanel'

function makeAccount(overrides: Partial<AccountView> = {}): AccountView {
  return {
    username: 'alice',
    role: 'member',
    enabled: true,
    created_at: '2026-10-17T00:00:00Z',
    revision: 1,
    ...overrides,
  }
}

interface FakeState {
  accounts: AccountView[]
  createCalls: AccountCreateInput[]
  updateCalls: Array<{ username: string; input: AccountUpdateInput }>
  resetCalls: Array<{ username: string; input: AccountPasswordResetInput }>
  ownCalls: OwnPasswordChangeInput[]
  nextError: ApiError | null
  listError: ApiError | null
}

function makeFakeApi(initial?: Partial<FakeState>): { api: AccountApi; state: FakeState } {
  const state: FakeState = {
    accounts: [makeAccount(), makeAccount({ username: 'root', role: 'admin', revision: 3 })],
    createCalls: [],
    updateCalls: [],
    resetCalls: [],
    ownCalls: [],
    nextError: null,
    listError: null,
    ...initial,
  }
  const maybeThrow = () => {
    if (state.nextError) {
      const error = state.nextError
      state.nextError = null
      throw error
    }
  }
  const api: AccountApi = {
    async listAccounts() {
      if (state.listError) throw state.listError
      return state.accounts.map((account) => ({ ...account }))
    },
    async createAccount(input) {
      state.createCalls.push(input)
      maybeThrow()
      const created = makeAccount({
        username: input.username,
        role: input.role,
        enabled: true,
        revision: 0,
      })
      state.accounts = [...state.accounts, created]
      return created
    },
    async updateAccount(username, input) {
      state.updateCalls.push({ username, input })
      maybeThrow()
      const index = state.accounts.findIndex((account) => account.username === username)
      const current = state.accounts[index]
      const updated: AccountView = {
        ...current,
        role: input.role ?? current.role,
        enabled: input.enabled ?? current.enabled,
        revision: current.revision + 1,
      }
      state.accounts[index] = updated
      return updated
    },
    async resetAccountPassword(username, input) {
      state.resetCalls.push({ username, input })
      maybeThrow()
      const index = state.accounts.findIndex((account) => account.username === username)
      const current = state.accounts[index]
      const updated = { ...current, revision: current.revision + 1 }
      state.accounts[index] = updated
      return updated
    },
    async changeOwnPassword(input) {
      state.ownCalls.push(input)
      maybeThrow()
      return { username: 'alice', signed_out: true }
    },
  }
  return { api, state }
}

beforeEach(() => {
  window.sessionStorage.clear()
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
})

describe('LG-062 My Account', () => {
  it('rejects a confirmation mismatch without calling the API', async () => {
    const { api, state } = makeFakeApi()
    render(<MyAccountPanel api={api} />)
    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'old-pw' },
    })
    fireEvent.change(screen.getByLabelText('New password'), {
      target: { value: 'new-pw' },
    })
    fireEvent.change(screen.getByLabelText('Confirm new password'), {
      target: { value: 'different' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText(/do not match/)).toBeInTheDocument()
    expect(state.ownCalls).toHaveLength(0)
  })

  it('changes the password, clears the fields and never persists them', async () => {
    const { api, state } = makeFakeApi()
    render(<MyAccountPanel api={api} />)
    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'old-secret-pw' },
    })
    fireEvent.change(screen.getByLabelText('New password'), {
      target: { value: 'new-secret-pw' },
    })
    fireEvent.change(screen.getByLabelText('Confirm new password'), {
      target: { value: 'new-secret-pw' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))

    await waitFor(() => expect(state.ownCalls).toHaveLength(1))
    expect(state.ownCalls[0]).toEqual({
      current_password: 'old-secret-pw',
      new_password: 'new-secret-pw',
      confirmation: 'new-secret-pw',
    })
    await waitFor(() => expect(screen.getByLabelText('Current password')).toHaveValue(''))
    expect(screen.getByLabelText('New password')).toHaveValue('')
    expect(screen.getByLabelText('Confirm new password')).toHaveValue('')
    expect(JSON.stringify(window.localStorage)).not.toContain('new-secret-pw')
    expect(JSON.stringify(window.sessionStorage)).not.toContain('new-secret-pw')
    expect(await screen.findByText(/Sign in again/)).toBeInTheDocument()
  })

  it('surfaces a wrong current password and still clears the fields', async () => {
    const { api, state } = makeFakeApi()
    state.nextError = new ApiError({
      message: 'current password is incorrect',
      code: 'unauthorized',
      httpStatus: 401,
      retryable: false,
    })
    render(<MyAccountPanel api={api} />)
    fireEvent.change(screen.getByLabelText('Current password'), {
      target: { value: 'wrong' },
    })
    fireEvent.change(screen.getByLabelText('New password'), {
      target: { value: 'new-pw' },
    })
    fireEvent.change(screen.getByLabelText('Confirm new password'), {
      target: { value: 'new-pw' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Change password' }))
    expect(await screen.findByText(/current password is incorrect/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Current password')).toHaveValue(''))
  })
})

describe('LG-062 Accounts admin panel', () => {
  it('lists accounts and changes a role with the current revision', async () => {
    const { api, state } = makeFakeApi()
    render(<AccountsPanel api={api} />)
    expect(await screen.findByText('alice')).toBeInTheDocument()
    expect(screen.getByText('root')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Role for alice'), {
      target: { value: 'admin' },
    })
    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0]).toEqual({
      username: 'alice',
      input: { role: 'admin', expected_revision: 1 },
    })
  })

  it('disables an account and shows the new status', async () => {
    const { api, state } = makeFakeApi()
    render(<AccountsPanel api={api} />)
    await screen.findByText('alice')
    fireEvent.click(screen.getAllByRole('button', { name: 'Disable' })[0])
    await waitFor(() => expect(state.updateCalls).toHaveLength(1))
    expect(state.updateCalls[0].input).toEqual({ enabled: false, expected_revision: 1 })
    expect(await screen.findByText('disabled')).toBeInTheDocument()
  })

  it('creates an account and clears the temporary password', async () => {
    const { api, state } = makeFakeApi()
    render(<AccountsPanel api={api} />)
    await screen.findByText('alice')
    fireEvent.click(screen.getByRole('button', { name: 'New account' }))
    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'carol' },
    })
    fireEvent.change(screen.getByLabelText('Temporary password'), {
      target: { value: 'carol-temp-pw' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    await waitFor(() => expect(state.createCalls).toHaveLength(1))
    expect(state.createCalls[0]).toEqual({
      username: 'carol',
      password: 'carol-temp-pw',
      role: 'member',
    })
    expect(await screen.findByText('carol')).toBeInTheDocument()
    expect(screen.queryByLabelText('Temporary password')).toBeNull()
    expect(JSON.stringify(window.localStorage)).not.toContain('carol-temp-pw')
  })

  it('resets a password with a transient field that is cleared', async () => {
    const { api, state } = makeFakeApi()
    render(<AccountsPanel api={api} />)
    await screen.findByText('alice')
    fireEvent.click(screen.getAllByRole('button', { name: 'Reset password' })[0])
    const field = await screen.findByLabelText('New temporary password')
    fireEvent.change(field, { target: { value: 'reset-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Set new password' }))
    await waitFor(() => expect(state.resetCalls).toHaveLength(1))
    expect(state.resetCalls[0]).toEqual({
      username: 'alice',
      input: { password: 'reset-secret' },
    })
    await waitFor(() => expect(screen.queryByLabelText('New temporary password')).toBeNull())
    expect(JSON.stringify(window.localStorage)).not.toContain('reset-secret')
  })

  it('shows the actionable last-administrator error from the backend', async () => {
    const { api, state } = makeFakeApi()
    state.nextError = new ApiError({
      message:
        'cannot disable or demote the last active administrator; promote or enable another admin first',
      code: 'illegal_transition',
      httpStatus: 409,
      retryable: false,
      details: { reason: 'last_active_admin' },
    })
    render(<AccountsPanel api={api} />)
    await screen.findByText('alice')
    fireEvent.click(screen.getAllByRole('button', { name: 'Disable' })[0])
    expect(
      await screen.findByText(/last active administrator; promote or enable another admin/),
    ).toBeInTheDocument()
  })

  it('surfaces a load failure with a retry affordance', async () => {
    const { api, state } = makeFakeApi()
    state.listError = new ApiError({
      message: 'account service unreachable',
      code: 'network_error',
      httpStatus: null,
      retryable: true,
    })
    render(<AccountsPanel api={api} />)
    expect(await screen.findByText(/Could not load accounts/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })
})

describe('LG-062 account capability', () => {
  const base = {
    status: 'ok',
    package_version: '0.1.0',
    schema_version: 'lightgravity.bot/v1',
    capabilities: { accounts: true },
    contract_version: '1.15.0',
  }
  it('requires contract >= 1.15 and the explicit accounts capability', () => {
    expect(supportsAccounts(base)).toBe(true)
    expect(supportsAccounts({ ...base, contract_version: '1.14.0' })).toBe(false)
    expect(supportsAccounts({ ...base, capabilities: {} })).toBe(false)
  })
})
