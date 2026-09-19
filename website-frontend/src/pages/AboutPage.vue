<script setup lang="ts">
const principles = [
  {
    title: '结论要能被检查',
    description: '分析过程中的每一步决策、使用的数据和检索到的资料都保留下来，观点可以逐条回溯。',
  },
  {
    title: '方法要跟数据走',
    description: '不同数据适合不同因果方法。智能体先做检查再选择算法，而不是固定套用一种模型。',
  },
  {
    title: '边界要写清楚',
    description: '公开能力与内部系统分开，权限、审计和受控操作的规则写在代码与文档里，不靠口头约定。',
  },
] as const

const contact = [
  { label: '产品与使用问题', value: '登录后在工作区提交问题，会随会话记录一起留存' },
  { label: '账号与权限', value: '由管理员在管理员系统中处理' },
  { label: '公开文档', value: '/docs 提供面向使用者的说明' },
] as const
</script>

<template>
  <div class="page">
    <header class="page-header">
      <p class="eyebrow">关于</p>
      <h1>把因果分析做得可复核</h1>
      <p class="section-summary">
        CausalAgent 面向需要解释清楚“为什么”的分析场景：数据规模不必很大，但结论必须站得住。
      </p>
    </header>

    <section class="section">
      <h2 class="section-title">我们坚持的原则</h2>
      <div class="card-grid">
        <article v-for="principle in principles" :key="principle.title" class="card">
          <h3>{{ principle.title }}</h3>
          <p>{{ principle.description }}</p>
        </article>
      </div>
    </section>

    <section class="section">
      <h2 class="section-title">联系方式</h2>
      <dl class="fact-grid">
        <div v-for="item in contact" :key="item.label" class="fact">
          <dt>{{ item.label }}</dt>
          <dd>{{ item.value }}</dd>
        </div>
      </dl>
    </section>
  </div>
</template>

