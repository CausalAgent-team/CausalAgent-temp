import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ThinkingStepDetails from '../../src/components/ThinkingStepDetails.vue'
import type { ThinkingStep } from '../../src/types/domain'

function step(): ThinkingStep {
  return {
    stepId: 's1',
    nodeName: 'deep_agent',
    title: '执行 Deep Agent 分析',
    status: 'in-progress',
    duration: null,
    details: [
      { kind: 'text', text: '载入数据', tone: 'default' },
      {
        kind: 'decision',
        key: 's1:algorithm:pc',
        decisionKind: 'algorithm',
        toolName: 'pc',
        streamId: 'decision-1',
        text: '一二',
        complete: true,
        pending: [],
      },
      {
        kind: 'decision',
        key: 's1:evidence:web_evidence_search',
        decisionKind: 'evidence',
        toolName: 'web_evidence_search',
        streamId: 'decision-2',
        text: '三四',
        complete: true,
        pending: [],
      },
    ],
  }
}

describe('ThinkingStepDetails', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('reveals public decisions one after another in arrival order', async () => {
    const wrapper = mount(ThinkingStepDetails, { props: { step: step(), animate: true } })
    expect(wrapper.get('.step-detail').text()).toBe('载入数据')

    await vi.advanceTimersByTimeAsync(25)
    expect(wrapper.text()).toContain('算法决策：一')
    expect(wrapper.text()).not.toContain('三四')

    await vi.advanceTimersByTimeAsync(75)
    expect(wrapper.text()).toContain('算法决策：一二')
    expect(wrapper.text()).toContain('检索决策：三四')
  })

  it('shows every detail at once when the job is no longer active', () => {
    const wrapper = mount(ThinkingStepDetails, { props: { step: step(), animate: false } })
    expect(wrapper.text()).toContain('算法决策：一二')
    expect(wrapper.text()).toContain('检索决策：三四')
  })
})
