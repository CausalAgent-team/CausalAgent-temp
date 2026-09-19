/* 公开文档内容：面向使用者的说明，与仓库内部开发文档分开维护。 */

export interface DocSection {
  id: string
  title: string
  paragraphs: readonly string[]
  bullets?: readonly string[]
}

export const DOC_INTRO = {
  title: '使用文档',
  summary:
    '这里介绍公开可用的功能与常见操作。面向开发者的内部设计说明保存在仓库的 Document 目录，不随本页发布。',
} as const

export const DOC_SECTIONS: readonly DocSection[] = [
  {
    id: 'start',
    title: '开始使用',
    paragraphs: [
      '在官网注册账号后即可进入工作区。工作区只对已登录用户开放，未登录访问会自动跳转到登录页面。',
    ],
    bullets: [
      '注册需要至少 3 个字符的用户名，密码至少 6 位并包含数字',
      '登录后默认进入工作区，也可以在退出后回到官网首页',
      '浏览器需要允许本站使用 Cookie 以保持登录状态',
    ],
  },
  {
    id: 'workspace',
    title: '工作区',
    paragraphs: [
      '工作区由会话、文件列表和输入框组成。每次分析都在一个会话里完成，历史会话可以随时回到并继续追问。',
    ],
    bullets: [
      '新建对话后描述分析目标，必要时上传数据文件',
      '任务执行过程以阶段和事件的形式显示，长任务可以取消',
      '左侧文件列表保存已上传的数据，可以复用或删除',
    ],
  },
  {
    id: 'results',
    title: '结果与报告',
    paragraphs: [
      '任务完成后会给出结论、图表和结构化报告。报告保留分析过程中使用的数据与知识来源，便于复核。',
    ],
    bullets: [
      '因果图展示变量之间的关系方向与强度',
      '报告分为流程、检索与评测三类视图，可切换查看',
      '开启联网检索时，引用来源会随回答列出',
    ],
  },
  {
    id: 'account',
    title: '账号与安全',
    paragraphs: [
      '账号状态、角色与权限由服务端决定。账号被禁用或权限变更后，已登录的浏览器会话会在下一次请求时失效。',
    ],
    bullets: [
      '忘记密码请联系管理员重置，重置后需要重新登录',
      '登录和注册入口分别为 /auth/sign-in 与 /auth/sign-up',
      '管理员功能与普通用户工作区相互独立，普通账号不能访问管理员页面',
    ],
  },
]

export const DOC_LINKS: ReadonlyArray<{ label: string; href: string; description: string }> = [
  { label: '产品能力', href: '/product', description: '了解智能体覆盖的分析环节' },
  { label: '更新日志', href: '/changelog', description: '查看公开版本的功能变化' },
  { label: '进入工作区', href: '/dashboard', description: '登录后开始一次分析' },
]

