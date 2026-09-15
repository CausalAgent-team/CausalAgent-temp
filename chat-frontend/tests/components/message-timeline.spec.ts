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
})
