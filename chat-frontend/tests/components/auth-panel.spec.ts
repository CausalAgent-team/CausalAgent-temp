import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AuthPanel from '../../src/components/AuthPanel.vue'

describe('AuthPanel', () => {
  it('emits trimmed credentials through the login boundary', async () => {
    const wrapper = mount(AuthPanel, { props: { busy: false, error: null } })
    await wrapper.get('input[autocomplete="username"]').setValue('  alice  ')
    await wrapper.get('input[autocomplete="current-password"]').setValue('secret')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('login')).toEqual([['alice', 'secret']])
  })
})
