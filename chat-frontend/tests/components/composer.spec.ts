import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import Composer from '../../src/components/Composer.vue'

describe('Composer', () => {
  it('emits draft, web-search and send actions without storing DOM resources', async () => {
    const wrapper = mount(Composer, {
      props: {
        draft: '',
        webSearchEnabled: false,
        selectedFile: null,
        activeJob: null,
        sending: false,
      },
    })
    await wrapper.get('textarea').setValue('hello')
    await wrapper.get('.web-search-button').trigger('click')
    await wrapper.get('textarea').trigger('keydown', { key: 'Enter', shiftKey: false })

    expect(wrapper.emitted('update:draft')).toEqual([['hello']])
    expect(wrapper.emitted('update:web-search')).toEqual([[true]])
    expect(wrapper.emitted('send')).toHaveLength(1)
  })
})
