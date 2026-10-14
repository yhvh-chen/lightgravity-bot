#!/usr/bin/env node
/**
 * Inline the built frontend into one self-contained HTML file (LG-011 helper).
 *
 * Some sandboxed environments allow `file://` pages but block loopback HTTP,
 * so the browser smoke check (tests/browser/shell-check.mjs) cannot point at a
 * `vite preview` server. This helper reads `dist/` after `npm run build` and
 * inlines the CSS/JS so `shell-check.mjs` can load it via `file://`.
 *
 * The output path is printed to stdout. No dependency is added.
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const frontendRoot = resolve(here, '..', '..')
const assetsDir = join(frontendRoot, 'dist', 'assets')
const outPath = process.env.INLINE_OUT ?? '/tmp/lg011-inline.html'

if (!existsSync(assetsDir)) {
  console.error('dist/assets not found — run `npm run build` first')
  process.exit(1)
}

const assets = readdirSync(assetsDir)
const js = assets.find((name) => name.endsWith('.js'))
const css = assets.find((name) => name.endsWith('.css'))
if (!js || !css) {
  console.error('dist/assets is missing the JS/CSS bundle')
  process.exit(1)
}

const jsSource = readFileSync(join(assetsDir, js), 'utf8')
if (jsSource.includes('</script')) {
  console.error('bundle contains </script and cannot be inlined safely')
  process.exit(1)
}

const html = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>LightGravity Bot</title>
    <style>${readFileSync(join(assetsDir, css), 'utf8')}</style>
  </head>
  <body>
    <div id="root"></div>
    <script type="module">${jsSource}</script>
  </body>
</html>
`

writeFileSync(outPath, html)
console.log(outPath)
