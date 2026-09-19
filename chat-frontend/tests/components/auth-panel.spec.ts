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

  it('shows the password on request without touching the value', async () => {
    const wrapper = mount(AuthPanel, { props: { busy: false, error: null } })
    await wrapper.get('#auth-password').setValue('secret')

    await wrapper.get('.password-toggle').trigger('click')
    expect(wrapper.get('#auth-password').attributes('type')).toBe('text')
    expect(wrapper.get<HTMLInputElement>('#auth-password').element.value).toBe('secret')

    await wrapper.get('.password-toggle').trigger('click')
    expect(wrapper.get('#auth-password').attributes('type')).toBe('password')
  })

  it('returns to the login form after a successful registration', async () => {
    const wrapper = mount(AuthPanel, { props: { busy: false, error: null, notice: null } })
    await wrapper.get('.link-button').trigger('click')
    expect(wrapper.get('h2').text()).toBe('注册')

    await wrapper.setProps({ notice: '注册成功！请登录。' })
    expect(wrapper.get('h2').text()).toBe('登录')
    expect(wrapper.get('.form-notice').text()).toBe('注册成功！请登录。')
  })

  it('closes on Escape and on a backdrop click when the panel is closeable', async () => {
    const wrapper = mount(AuthPanel, { props: { busy: false, error: null, closeable: true } })

    await wrapper.get('.auth-panel').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)

    globalThis.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('close')).toHaveLength(2)

    wrapper.unmount()
  })

  it('keeps Tab focus inside the card while the panel is open', async () => {
    const wrapper = mount(AuthPanel, { props: { busy: false, error: null, closeable: true }, attachTo: document.body })
    const buttons = wrapper.get('.auth-card').element.querySelectorAll('button')
    const lastButton = buttons.item(buttons.length - 1)
    lastButton.focus()

    globalThis.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab' }))
    expect(document.activeElement).toBe(wrapper.get('#auth-username').element)

    globalThis.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true }))
    expect(document.activeElement).toBe(lastButton)

    wrapper.unmount()
  })
})
