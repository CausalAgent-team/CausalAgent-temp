import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import MessageTimeline from '../../src/components/MessageTimeline.vue'
import { useJobsStore } from '../../src/stores/jobs.store'

describe('MessageTimeline', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('keeps a live final result visible outside the collapsible thinking panel', () => {
    const jobs = useJobsStore()
    const job = jobs.startFromResponse('job-1', 'session-1', 'running')
    job.thinking.status = 'completed'
    job.thinking.finalResult = { type: 'text', summary: '实时分析结果' }

    const wrapper = mount(MessageTimeline, {
      props: {
        messages: [{
          localId: 'message-1',
          sender: 'user',
          text: '请开始分析',
          analysisJobId: 'job-1',
        }],
      },
    })

    expect(wrapper.get('.thinking-block')).toBeTruthy()
    expect(wrapper.get('.message.ai-message').text()).toContain('实时分析结果')
  })

  it('shows a public decision with its own prefix inside the step details', async () => {
    const jobs = useJobsStore()
    const job = jobs.startFromResponse('job-1', 'session-1', 'running')
    job.thinking.status = 'completed'
    job.thinking.stepOrder = ['s1']
    job.thinking.steps = {
      s1: {
        stepId: 's1',
        nodeName: 'deep_agent',
        title: '执行 Deep Agent 分析',
        status: 'completed',
        duration: 1.2,
        details: [
          { kind: 'text', text: '调用工具：pc（参数字段：data）', tone: 'default' },
          {
            kind: 'decision',
            key: 's1:algorithm:pc',
            decisionKind: 'algorithm',
            toolName: 'pc',
            streamId: 'decision-1',
            text: '选择 PC，因为样本充足',
            complete: true,
            pending: [],
          },
        ],
      },
    }

    const wrapper = mount(MessageTimeline, {
      props: {
        messages: [{
          localId: 'message-1',
          sender: 'user',
          text: '请开始分析',
          analysisJobId: 'job-1',
        }],
      },
    })

    await wrapper.get('.step-header').trigger('click')
    const details = wrapper.get('.step-details')
    expect(details.isVisible()).toBe(true)
    expect(details.text()).toContain('调用工具：pc（参数字段：data）')
    expect(details.text()).toContain('算法决策：选择 PC，因为样本充足')
  })
})
