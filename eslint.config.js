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
  {
    // 仓库根 `scripts/` 是 Node 原生工具（#70 的字典检查器），不属于任何 TS 工程：
    // 根目录没有 tsconfig.json、也没有 @types/node。若沿用上面的 projectService，
    // 会得到大量「type that could not be resolved」解析噪声；若整目录 ignore，
    // 又会让新增脚本失去语法与规则检查。
    //
    // 因此这里只对这一个目录**关掉类型感知**（保留 eslint 规则本身）：
    // - projectService: false —— 走默认 parser，不再要求文件属于某个 tsconfig；
    // - disableTypeChecked —— 关掉依赖类型信息的规则（no-unsafe-* 等）。
    // 类型层由该目录自己的 `node --test` 与运行时断言覆盖，而不是假装有 TS 工程。
    files: ['scripts/**/*.mjs'],
    ...tseslint.configs.disableTypeChecked,
    languageOptions: {
      parserOptions: {
        projectService: false,
      },
    },
    rules: {
      ...tseslint.configs.disableTypeChecked.rules,
      // 脚本用 console 输出检查结果，这是它的正常产出渠道，不是调试残留。
      'no-console': 'off',
    },
  },
)
