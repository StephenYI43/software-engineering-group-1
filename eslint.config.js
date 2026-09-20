import tseslint from 'typescript-eslint'

// 根级 flat config，覆盖整个 workspace。
// `ignores` 是必需的，不是风格偏好：projectService 会尝试把 eslint.config.js 本身
// 纳入类型工程，而它不在任何 tsconfig 的 include 内，缺了这条会报
// `Parsing error: ... was not found by the project service`。
// 见 docs/adr/0003-web-toolchain.md「必要的忽略规则」。
export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/node_modules/**',
      'eslint.config.js',
      // 后端虚拟环境里混有 JS 产物（例如 coverage 的 HTML 报告资源）。
      // 不加这条，根级 `eslint .` 会去解析 .venv 里的第三方 JS 并报
      // 「not found by the project service」。
      '**/.venv/**',
      '**/__pycache__/**',
      '**/coverage/**',
    ],
  },
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
  },
)
