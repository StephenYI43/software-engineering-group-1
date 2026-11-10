import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    // 与 apps/web 一致：显式清理每个用例的 DOM，见 src/test-setup.ts。
    setupFiles: ['./src/test-setup.ts'],
  },
})
