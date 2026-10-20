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
      // 仓库根 scripts/ 是 Node 原生工具（#70 的字典检查器），不属任何 TS 工程：
      // 根目录没有 tsconfig.json、也没有 @types/node，硬纳入 projectService 会得到
      // 486 条「type that could not be resolved」，全是解析噪声而非代码问题。
      // 该目录的验证手段是 `node --test scripts/`，不是类型检查——所以这里忽略，
      // 而不是给它装一套只为 lint 存在的依赖。
      'scripts/**',
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
