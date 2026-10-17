/**
 * Account-management API client (LG-062; docs/08 §16, additive 1.15).
 *
 * Two surfaces:
 *
 * * admin-only `/accounts*` — list/create/enable/disable/role/reset;
 * * `/account/password` — every authenticated team user changes their own
 *   password using the session cookie identity (never a body username).
 *
 * Identity is the HttpOnly team session cookie, so the team runtime token is
 * deliberately *not* sent here.  Passwords are write-only: they are sent once
 * and never read back or persisted by this module.
 */

import { apiRequest } from './client'

export type AccountRole = 'admin' | 'member'

/** Whitelisted account view; never carries a password, salt or hash. */
export interface AccountView {
  username: string
  role: AccountRole
  enabled: boolean
  created_at: string
  revision: number
}

export interface AccountCreateInput {
  username: string
  password: string
  role: AccountRole
}

export interface AccountUpdateInput {
  role?: AccountRole
  enabled?: boolean
  expected_revision?: number
}

export interface AccountPasswordResetInput {
  password: string
  expected_revision?: number
}

export interface OwnPasswordChangeInput {
  current_password: string
  new_password: string
  confirmation: string
}

export interface OwnPasswordChangeResult {
  username: string
  signed_out: boolean
}

export interface AccountApi {
  listAccounts(signal?: AbortSignal): Promise<AccountView[]>
  createAccount(input: AccountCreateInput, signal?: AbortSignal): Promise<AccountView>
  updateAccount(
    username: string,
    input: AccountUpdateInput,
    signal?: AbortSignal,
  ): Promise<AccountView>
  resetAccountPassword(
    username: string,
    input: AccountPasswordResetInput,
    signal?: AbortSignal,
  ): Promise<AccountView>
  changeOwnPassword(
    input: OwnPasswordChangeInput,
    signal?: AbortSignal,
  ): Promise<OwnPasswordChangeResult>
}

function encodeUsername(username: string): string {
  return encodeURIComponent(username)
}

function jsonHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json' }
}

/** Bind to the real `/api/v1` routes; no token is attached (session cookie). */
export function createAccountsApi(): AccountApi {
  return {
    async listAccounts(signal) {
      const body = await apiRequest<{ accounts: AccountView[] }>('/accounts', { signal })
      return body.accounts
    },

    createAccount(input, signal) {
      return apiRequest<AccountView>('/accounts', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify(input),
        signal,
      })
    },

    updateAccount(username, input, signal) {
      return apiRequest<AccountView>(`/accounts/${encodeUsername(username)}`, {
        method: 'PATCH',
        headers: jsonHeaders(),
        body: JSON.stringify(input),
        signal,
      })
    },

    resetAccountPassword(username, input, signal) {
      return apiRequest<AccountView>(
        `/accounts/${encodeUsername(username)}/password`,
        {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify(input),
          signal,
        },
      )
    },

    changeOwnPassword(input, signal) {
      return apiRequest<OwnPasswordChangeResult>('/account/password', {
        method: 'POST',
        headers: jsonHeaders(),
        body: JSON.stringify(input),
        signal,
      })
    },
  }
}
