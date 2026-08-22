// Runs once before every test file (see vitest.config.js's `test.setupFiles`).
// Extends Vitest's `expect` with the jest-dom matchers (toBeInTheDocument,
// toHaveValue, toBeDisabled, ...) used throughout the test files under
// src/pages/. The jsdom test environment itself is configured in
// vitest.config.js, not here.
import '@testing-library/jest-dom/vitest'

import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// @testing-library/react only registers its own automatic afterEach(cleanup)
// when it detects Vitest's *globals* (test.globals: true in vitest.config.js).
// That's deliberately off here (see vitest.config.js's comment), so without
// this, a component rendered in one test would stay mounted into the next
// test in the same file - e.g. two CoverageEditor renders both leaving their
// "Von" inputs in the DOM at once.
afterEach(() => {
  cleanup()
})
