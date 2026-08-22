import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Separate from vite.config.js (rather than merged via `mergeConfig`)
// because the two run in genuinely different contexts - one builds/serves
// the app, the other only needs enough of Vite to transform JSX for tests -
// but the `react()` plugin is still shared so both transform JSX the same
// way. `test.globals` is deliberately left at its default (false): test
// files import `describe`/`it`/`expect`/... from 'vitest' explicitly, so
// eslint.config.js doesn't need a vitest globals entry to stay clean.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
  },
})
