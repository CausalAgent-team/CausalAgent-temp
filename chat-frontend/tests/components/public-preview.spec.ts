import { mount } from '@vue/test-utils'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import PublicPreview from '../../src/components/PublicPreview.vue'
import markedSource from '../../public/vendor/marked.min.js?raw'

/*
 * jsdom 没有 canvas，vis-network 无法真实实例化；这里只替换第三方图形库本身，
 * 用来验证预览示例能走真实渲染链路，不当作真实图形渲染的验收。
 */
vi.mock('vis-network/standalone', () => ({
  Network: class {
    on(): void {}
    setOptions(): void {}
    setData(): void {}
    destroy(): void {}
  },
}))

beforeAll(() => {
  new Function(markedSource).call(window)
})

function mountPreview(demoKey: 'overview' | 'report' | 'graph' = 'overview') {
  return mount(PublicPreview, {
    props: { draft: '', webSearchEnabled: false, demoKey },
  })
}

describe('PublicPreview', () => {
  it('renders the product explanation and the static sample conversation', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountPreview()

    expect(wrapper.get('.preview-badge').text()).toBe('公开预览')
    expect(wrapper.get('.preview-hero h1').text()).toContain('把数据交给 Agent')
    expect(wrapper.findAll('.preview-features li')).toHaveLength(3)
    expect(wrapper.get('.preview-demo-head h2').text()).toBe('销售数据因果分析')
    expect(wrapper.findAll('.preview-session-item')).toHaveLength(3)
    expect(wrapper.get('.preview-messages').text()).toContain('价格和销量之间是什么关系')
    expect(wrapper.get('.preview-lock-note').text()).toContain('需要先登录或注册')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('asks for login instead of sending when a visitor clicks send', async () => {
    const wrapper = mount(PublicPreview, {
      props: { draft: '未登录时的文字草稿', webSearchEnabled: false, demoKey: 'overview' },
    })
    await wrapper.get('.send-button').trigger('click')

    expect(wrapper.emitted('request-auth')).toEqual([['send']])
    expect(wrapper.emitted('send')).toBeUndefined()
    expect(wrapper.emitted('upload')).toBeUndefined()
  })

  it('asks for login instead of opening the file picker when a visitor clicks upload', async () => {
    const wrapper = mountPreview()
    await wrapper.get('.upload-button').trigger('click')

    expect(wrapper.emitted('request-auth')).toEqual([['upload']])
    expect(wrapper.emitted('upload')).toBeUndefined()
  })

  it('keeps the typed draft in the preview composer', async () => {
    const wrapper = mountPreview()
    await wrapper.get('textarea').setValue('刷新后应该恢复的文字')

    expect(wrapper.emitted('update:draft')).toEqual([['刷新后应该恢复的文字']])
    expect(wrapper.get('textarea').element.value).toBe('刷新后应该恢复的文字')
  })

  it('reports the sample the visitor opens', async () => {
    const wrapper = mountPreview()
    const items = wrapper.findAll('.preview-session-item')
    await items[2]?.trigger('click')

    expect(wrapper.emitted('demo-open')).toEqual([['graph']])
  })

  it('renders the static structured report through the real renderer', () => {
    const wrapper = mountPreview('report')

    expect(wrapper.get('.report-title').text()).toBe('价格与销量的因果关系分析')
    expect(wrapper.findAll('.report-histogram-svg rect')).toHaveLength(4)
    expect(wrapper.get('.report-causal-graph-title').text()).toBe('主要因果关系')
  })

  it('renders the static causal graph sample', () => {
    const wrapper = mountPreview('graph')

    expect(wrapper.get('.causal-report .markdown-content').text()).toContain('4 条边')
    expect(wrapper.get('.causal-graph-container')).toBeTruthy()
  })
})
