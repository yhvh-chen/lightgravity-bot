/**
 * LG-055 non-browser API smoke over the isolated real backend.
 *
 * Uses Playwright's APIRequestContext only (no browser is launched), so this
 * runs even where no browser binary is available.  It proves the harness
 * backends really serve the LG-054 contract and real persistence.
 */
import { expect, request as playwrightRequest, test } from '@playwright/test'

import { ACCOUNTS, loginApi, teamUrl, uniqueToken } from '../lib/helpers'

test.describe('LG-055 real HTTP API smoke (no browser)', () => {
  test('health and version advertise the LG-054 contract and capabilities', async () => {
    const api = await playwrightRequest.newContext({ baseURL: teamUrl() })
    try {
      const health = await api.get('/api/v1/health')
      expect(health.ok()).toBeTruthy()
      const body = (await health.json()) as {
        contract_version: string
        capabilities: Record<string, boolean>
      }
      expect(body.contract_version).toBe('1.16.0')
      expect(body.capabilities.global_chat).toBe(true)
      expect(body.capabilities.personal_chat).toBe(true)
      // LG-062 additive team-only account management.
      expect(body.capabilities.accounts).toBe(true)

      const version = await api.get('/api/v1/version')
      expect(((await version.json()) as { contract_version: string }).contract_version).toBe(
        '1.16.0',
      )
    } finally {
      await api.dispose()
    }
  })

  test('anonymous private chat is default-deny; private history is per-identity', async () => {
    const anon = await playwrightRequest.newContext({ baseURL: teamUrl() })
    const alice = await playwrightRequest.newContext({ baseURL: teamUrl() })
    const bob = await playwrightRequest.newContext({ baseURL: teamUrl() })
    const admin = await playwrightRequest.newContext({ baseURL: teamUrl() })
    try {
      expect((await anon.get('/api/v1/conversations/personal/messages')).status()).toBe(401)
      await loginApi(alice, ACCOUNTS.alice)
      await loginApi(bob, ACCOUNTS.bob)
      await loginApi(admin, ACCOUNTS.admin)

      const token = uniqueToken('private-api')
      const sent = await alice.post('/api/v1/conversations/personal/messages', {
        data: { message_id: uniqueToken('msg'), content: token },
      })
      expect(sent.ok(), await sent.text()).toBeTruthy()

      const own = JSON.stringify(await (await alice.get('/api/v1/conversations/personal/messages')).json())
      expect(own).toContain(token)
      for (const other of [bob, admin]) {
        const history = JSON.stringify(
          await (await other.get('/api/v1/conversations/personal/messages')).json(),
        )
        expect(history).not.toContain(token)
      }
      const shared = JSON.stringify(
        await (await alice.get('/api/v1/conversations/global/messages')).json(),
      )
      expect(shared).not.toContain(token)
    } finally {
      for (const ctx of [anon, alice, bob, admin]) await ctx.dispose()
    }
  })

  test('a Personal delivery request is chat-only (no Task created)', async () => {
    const alice = await playwrightRequest.newContext({ baseURL: teamUrl() })
    try {
      await loginApi(alice, ACCOUNTS.alice)
      const before = (await (await alice.get('/api/v1/tasks')).json()) as { items: unknown[] }
      const sent = await alice.post('/api/v1/conversations/personal/messages', {
        data: {
          message_id: uniqueToken('msg'),
          content: 'implement a brand new feature in the product',
        },
      })
      expect(sent.ok(), await sent.text()).toBeTruthy()
      const body = (await sent.json()) as { kind: string; data: Record<string, unknown> }
      expect(body.kind).toBe('switch_to_team')
      expect(body.data.creates_task).toBe(false)
      const after = (await (await alice.get('/api/v1/tasks')).json()) as { items: unknown[] }
      expect(after.items.length).toBe(before.items.length)
    } finally {
      await alice.dispose()
    }
  })
})
