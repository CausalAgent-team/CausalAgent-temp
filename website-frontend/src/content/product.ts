/* 官网产品内容：类型化数据，页面只负责排版。 */

export interface Feature {
  key: string
  title: string
  summary: string
  bullets: readonly string[]
}

export interface WorkflowStep {
  key: string
  title: string
  description: string
}

export interface DownloadOption {
  label: string
  description: string
  href: string | null
  action: string
}

export const HERO = {
  title: '把因果推断放进可复核的分析流程',
  summary:
    'CausalAgent 把数据文件、内部知识库和公开资料组织进同一条分析链路，自动完成数据检查、算法选择、结果解释与报告输出。',
  primaryAction: { label: '进入工作区', href: '/dashboard' },
  secondaryAction: { label: '了解产品', href: '/product' },
} as const

export const FEATURES: readonly Feature[] = [
  {
    key: 'intake',
    title: '数据与知识一起进入',
    summary: '上传结构化数据文件，同时引用内部知识库，让分析建立在可追溯的材料上。',
    bullets: [
      '支持表格数据文件上传与复用，历史文件随会话保留',
      '知识库检索结果携带来源，回答可以逐条回溯',
      '联网检索按需开启，公开资料与内部分析分开记录',
    ],
  },
  {
    key: 'causal',
    title: '按数据特征选择因果方法',
    summary: '先检查数据分布与约束，再选择拿得准的因果推断方法，避免套用固定模板。',
    bullets: [
      '自动做缺失值、量纲与共线性检查',
      '在因果发现与效应估计之间分步推进',
      '每一步决策及其依据随任务事件公开',
    ],
  },
  {
    key: 'trace',
    title: '过程可见，结论可复核',
    summary: '分析过程以结构化事件流展示，报告、图表和因果图都可以回到原始步骤。',
    bullets: [
      '执行阶段、算法选择与结论在同一时间线上呈现',
      '结构化报告可导出，图表与因果图随报告保存',
      '出现分歧或需要补数据时可以追问同一任务',
    ],
  },
  {
    key: 'ops',
    title: '可维护的运行方式',
    summary: '面向长期使用设计：任务排队、失败恢复、权限与审计都有明确的边界。',
    bullets: [
      '任务具备幂等键、租约与恢复机制',
      '管理员可以查看会话、任务与文件的使用情况',
      '敏感读取与受控写入都留下审计记录',
    ],
  },
]

export const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  {
    key: 'describe',
    title: '描述问题',
    description: '用自然语言说明分析目标，需要时上传统计数据文件并勾选是否需要联网检索。',
  },
  {
    key: 'run',
    title: '让智能体执行',
    description: '智能体检查数据、选择方法、运行算法，并把阶段性结论与依据持续展示出来。',
  },
  {
    key: 'review',
    title: '复核并取用结论',
    description: '查看因果图、指标与结构化报告，将结论带回业务讨论或继续追问。',
  },
]

export const DOWNLOADS: readonly DownloadOption[] = [
  {
    label: 'Windows 桌面客户端',
    description: '适合日常使用的独立窗口，登录后直接进入工作区。',
    href: null,
    action: '在发布页获取安装包',
  },
  {
    label: '浏览器访问',
    description: '无需安装，使用任意现代浏览器打开本站并登录即可。',
    href: '/dashboard',
    action: '进入工作区',
  },
]

export const PLATFORM_FACTS: ReadonlyArray<{ label: string; value: string }> = [
  { label: '支持的输入', value: '表格数据文件、内部知识库、公开资料' },
  { label: '输出形态', value: '因果图、指标表、结构化报告' },
  { label: '会话保存', value: '历史会话与文件随账号保留' },
  { label: '权限模型', value: '角色与权限分离，按功能授权' },
]

