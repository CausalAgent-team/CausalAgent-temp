import type { PreviewDemoKey, PreviewPageId } from '../runtime/analytics/analytics-client'
import type { ChatMessage, ReportDocument } from '../types/domain'

/*
 * 公开预览的静态示例数据。它只在前端渲染，不经过任何公开数据接口，
 * 因此未登录访客不会因为浏览示例而创建 Session、消息、文件或分析 Job。
 */

export const PUBLIC_PREVIEW_PAGE_ID: PreviewPageId = 'home'

export interface PublicPreviewDemo {
  key: PreviewDemoKey
  title: string
  description: string
  messages: ChatMessage[]
}

const reportDocument: ReportDocument = {
  schema_version: 1,
  report_id: 'preview_report_price_sales',
  title: '价格与销量的因果关系分析',
  blocks: [
    {
      id: 'section_summary',
      type: 'section',
      title: '结论摘要',
      children: [
        {
          id: 'markdown_summary',
          type: 'markdown',
          content: '## 主要结论\n\n- 价格与销量之间存在**负向**关系，在控制地区与季节后依然成立\n- 促销强度是价格影响销量的中介变量\n- 样本量 1200，缺失值比例 2.5%\n\n| 变量 | 关系 | 置信度 |\n| --- | --- | --- |\n| price | 负向 | 0.83 |\n| promotion | 正向 | 0.71 |',
          evidence_refs: ['evidence_price'],
        },
      ],
    },
    { id: 'chart_price', type: 'chart', title: '价格分布', asset_key: 'chart_histogram_price' },
    { id: 'chart_region', type: 'chart', title: '各区域平均销量', asset_key: 'chart_bar_region' },
    {
      id: 'section_graph',
      type: 'section',
      title: '因果关系',
      children: [
        {
          id: 'markdown_graph',
          type: 'markdown',
          content: '下图是算法在 1200 条样本上发现的因果关系，边标签为估计权重。',
        },
        { id: 'graph_price_sales', type: 'causal_graph', title: '主要因果关系', asset_key: 'graph_price_sales' },
      ],
    },
  ],
  assets: {
    chart_histogram_price: {
      asset_key: 'chart_histogram_price',
      type: 'chart',
      chart_type: 'histogram',
      data: { bins: [10, 20, 30, 40, 50], counts: [6, 18, 24, 9] },
      metadata: { variable: 'price' },
      options: { show_tooltip: true },
    },
    chart_bar_region: {
      asset_key: 'chart_bar_region',
      type: 'chart',
      chart_type: 'bar',
      data: { categories: ['华东', '华南', '华北', '西南'], counts: [420, 380, 265, 135] },
      metadata: { variable: 'region' },
    },
    graph_price_sales: {
      graph_id: 'graph_price_sales',
      schema_version: 1,
      nodes: [
        { id: 'node_price', variable: 'price', label: 'price' },
        { id: 'node_promotion', variable: 'promotion', label: 'promotion' },
        { id: 'node_season', variable: 'season', label: 'season' },
        { id: 'node_sales', variable: 'sales', label: 'sales' },
      ],
      edges: [
        { id: 'edge_price_sales', source: 'node_price', target: 'node_sales', edge_type: 'directed', weight: -0.42 },
        { id: 'edge_promotion_sales', source: 'node_promotion', target: 'node_sales', edge_type: 'directed', weight: 0.31 },
        { id: 'edge_season_sales', source: 'node_season', target: 'node_sales', edge_type: 'directed', weight: 0.18 },
        { id: 'edge_price_promotion', source: 'node_price', target: 'node_promotion', edge_type: 'undirected', weight: null },
      ],
    },
  },
  sources: [
    { source_id: 'src_preview', kind: 'file', title: 'sales_preview.csv', file_id: null },
  ],
  evidence_refs: [
    {
      evidence_id: 'evidence_price',
      source_ids: ['src_preview'],
      locator: { column: 'price' },
      description: '价格与销量的相关系数与回归结果',
    },
  ],
}

export const publicPreviewDemos: PublicPreviewDemo[] = [
  {
    key: 'overview',
    title: '销售数据因果分析',
    description: '示例对话：提出问题后，Agent 规划分析步骤并给出结论。',
    messages: [
      {
        localId: 'preview-overview-user',
        sender: 'user',
        text: '这份销售数据里，价格和销量之间是什么关系？',
      },
      {
        localId: 'preview-overview-ai',
        sender: 'ai',
        text: '我会先检查数据结构与缺失值，再运行因果发现算法。\n\n## 分析结果\n\n- 价格与销量之间存在**负向**关系，价格每上升 1 个单位，销量平均下降 0.42 个标准差\n- 促销强度是价格影响销量的中介变量\n- 地区与季节作为调整变量后，结论保持一致\n\n样本量 1200，缺失值比例 2.5%，算法为 PC 算法。',
      },
    ],
  },
  {
    key: 'report',
    title: '结构化分析报告',
    description: '示例报告：结论、图表与因果关系组织在一份报告文档里。',
    messages: [
      {
        localId: 'preview-report-user',
        sender: 'user',
        text: '把价格和销量的分析整理成一份完整的报告。',
      },
      {
        localId: 'preview-report-ai',
        sender: 'ai',
        text: {
          type: 'report',
          layout: 'report',
          render_mode: 'structured',
          document: reportDocument,
        },
      },
    ],
  },
  {
    key: 'graph',
    title: '因果关系图',
    description: '示例因果图：算法发现的主要因果关系与估计权重。',
    messages: [
      {
        localId: 'preview-graph-user',
        sender: 'user',
        text: '只展示算法发现的因果关系图。',
      },
      {
        localId: 'preview-graph-ai',
        sender: 'ai',
        text: {
          type: 'causal_graph',
          summary: '算法在 1200 条样本上发现 4 条边，其中价格到销量为负向关系。',
          data: {
            nodes: [
              { id: 'price', label: 'price' },
              { id: 'promotion', label: 'promotion' },
              { id: 'season', label: 'season' },
              { id: 'sales', label: 'sales' },
            ],
            edges: [
              { from: 'price', to: 'sales', arrows: 'to', dashes: false, label: '-0.42' },
              { from: 'promotion', to: 'sales', arrows: 'to', dashes: false, label: '0.31' },
              { from: 'season', to: 'sales', arrows: 'to', dashes: false, label: '0.18' },
              { from: 'price', to: 'promotion', arrows: '', dashes: true },
            ],
          },
        },
      },
    ],
  },
]

export function publicPreviewDemo(key: PreviewDemoKey): PublicPreviewDemo {
  const demo = publicPreviewDemos.find((candidate) => candidate.key === key)
  if (!demo) throw new Error('公开预览示例标识未登记：' + key)
  return demo
}
