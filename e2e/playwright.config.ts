import { existsSync } from 'node:fs'

import { defineConfig, devices, type Project } from '@playwright/test'

// Prefer the machine's real Chrome when present (no browser download needed).
const chrome =
  process.env.CHROME_BIN ??
  (existsSync('/usr/bin/google-chrome') ? '/usr/bin/google-chrome' : undefined)

const projects: Project[] = [
  { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
]
// Optional second engine; enable with `LG_E2E_FIREFOX=1` after
// `npx playwright install firefox` (Playwright ships its own Firefox build).
if (process.env.LG_E2E_FIREFOX === '1') {
  projects.push({ name: 'firefox', use: { ...devices['Desktop Firefox'] } })
}

/**
 * LG-055 Playwright configuration.
 *
 * The harness starts its own isolated real backends in `global-setup.ts`
 * (fresh temp data roots, deterministic responder, no product model).  It does
 * not use the developer's 8123/5173 services and never mocks API responses.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: true,
  retries: process.env.LG_E2E_RETRIES ? Number(process.env.LG_E2E_RETRIES) : 0,
  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: '/tmp/lg051-playwright-report' }],
    ['json', { outputFile: '/tmp/lg051-playwright-results.json' }],
  ],
  outputDir: '/tmp/lg051-playwright-artifacts',
  globalSetup: './global-setup.ts',
  use: {
    baseURL:
      process.env.LG_E2E_TEAM_URL ??
      `http://127.0.0.1:${process.env.LG_E2E_TEAM_PORT ?? 8791}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    ...(chrome
      ? { launchOptions: { executablePath: chrome, args: ['--no-sandbox'] } }
      : {}),
  },
  projects,
})
