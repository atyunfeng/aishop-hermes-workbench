import { readFile } from 'node:fs/promises'
import { resolve } from 'node:path'

import { build } from 'esbuild'


const allowedImports = new Set(['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'])
const output = resolve(import.meta.dirname, '../../hermes-plugin/desktop/plugin.js')

await build({
  entryPoints: [resolve(import.meta.dirname, '../src/plugin.tsx')],
  outfile: output,
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: 'es2022',
  jsx: 'automatic',
  external: [...allowedImports],
})

const bundle = await readFile(output, 'utf8')
const imports = [...bundle.matchAll(/\bfrom\s+["']([^"']+)["']|\bimport\s+["']([^"']+)["']/g)]
  .map(match => match[1] ?? match[2])
  .filter(specifier => !specifier.startsWith('.') && !specifier.startsWith('/'))
const unexpected = imports.filter(specifier => !allowedImports.has(specifier))
if (unexpected.length > 0) {
  throw new Error(`Unsupported desktop plugin imports: ${[...new Set(unexpected)].join(', ')}`)
}
