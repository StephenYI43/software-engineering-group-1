import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

/**
 * 直接指向 packages/ui 的源码入口。
 *
 * 为什么用 `fileURLToPath` 而不是 `new URL(...).pathname`：仓库路径可能包含非
 * ASCII 字符（本项目的工作副本路径里就有中文），`.pathname` 会把它们百分号编码，
 * 得到一个磁盘上不存在的路径。`fileURLToPath` 会正确解码。
 *
 * 跨包引源码而不是构建产物，是 ADR-0003「根级 workspace」决策的目的；
 * 若无此别名，须在 server.fs.allow 上额外放开工作区根目录。
 */
const uiEntry = fileURLToPath(new URL('../../packages/ui/src/index.ts', import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@pkg/ui': uiEntry,
    },
  },
  server: {
    // 允许 dev server 读取 apps/web 之外的 packages/ui 源码。
    fs: { allow: ['../..'] },
  },
  test: {
    environment: 'jsdom',
    // 显式清理每个用例的 DOM，见 src/test-setup.ts 的说明。
    setupFiles: ['./src/test-setup.ts'],
  },
})
