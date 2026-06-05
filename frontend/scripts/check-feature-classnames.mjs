#!/usr/bin/env node
// Ratchet guard for the "no styling in features" rule.
//
// Convention: feature files (src/features/**) hold data + business logic +
// composition only. All visual styling lives in src/components/ui/*. Practically
// that means NO `className=` (raw Tailwind) in features.
//
// We can't flip that on at once (~1900 existing usages), so this ratchets:
// the count may only go DOWN. Adding a className in a feature fails the check;
// removing some lets you lower the baseline. Goal: drive baseline → 0.
//
// Run: node scripts/check-feature-classnames.mjs   (npm: bun run lint:features)

import { readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const featuresDir = join(root, 'src', 'features')
const baselineFile = join(root, 'scripts', '.feature-classname-baseline')

function walk(dir) {
  const out = []
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name)
    if (e.isDirectory()) out.push(...walk(p))
    else if (/\.(tsx?|jsx?)$/.test(e.name) && !/\.(test|spec)\./.test(e.name)) out.push(p)
  }
  return out
}

let count = 0
for (const f of walk(featuresDir)) {
  count += (readFileSync(f, 'utf8').match(/className=/g) || []).length
}

const baseline = Number(readFileSync(baselineFile, 'utf8').trim())

if (process.argv.includes('--update')) {
  writeFileSync(baselineFile, `${count}\n`)
  console.log(`baseline updated → ${count}`)
  process.exit(0)
}

if (count > baseline) {
  console.error(
    `✗ feature className count rose: ${count} > baseline ${baseline}.\n` +
    `  Features must not add raw styling — compose components/ui primitives instead.\n` +
    `  See scripts/check-feature-classnames.mjs.`,
  )
  process.exit(1)
}

if (count < baseline) {
  console.log(`✓ ${count} classNames (down from ${baseline}). Run with --update to lock the lower baseline.`)
} else {
  console.log(`✓ feature className count holding at ${count}.`)
}
