/* 公开更新日志：只记录面向使用者的变化，内部开发日志保存在仓库 CHANGELOG.md。 */

export interface ChangelogEntry {
  version: string
  date: string
  status: string
  highlights: readonly string[]
  items: readonly string[]
}

export const CHANGELOG_INTRO = {
  title: '更新日志',
  summary:
    '本页只公开影响使用方式的变化。仓库内部的开发日志按提交持续追加，不在本页展示历史细节。',
} as const

export const CHANGELOG_ENTRIES: readonly ChangelogEntry[] = [
  {
    version: '0.2.0',
    date: '2026-09-19',
    status: '当前版本',
    highlights: [
      '官网、普通用户工作区、RAG 评测台与管理员系统按路径分开，各自使用独立构建产物',
      '登录与注册统一到 /auth/sign-in 和 /auth/sign-up',
      '账号授权改为角色与权限分离的模型',
    ],
    items: [
      '官网提供产品介绍、公开文档与更新日志，未登录访客也可以浏览',
      '普通用户工作区固定在 /dashboard，未登录访问跳转登录页面',
      'RAG 评测台移动到 /rag-eval，仅管理员可访问，页面与接口使用同一权限边界',
      '登录后的回跳地址只接受站内已登记路径，外部地址会被忽略',
      '账号角色或状态变化后，旧的登录会话会在下一次请求时失效',
    ],
  },
]

