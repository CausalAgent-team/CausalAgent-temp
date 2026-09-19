/* 官网页面路由：Flask 为每个公开路径返回同一份构建产物，这里只按 pathname 选择页面。 */

export type SitePageName =
  | 'home'
  | 'product'
  | 'about'
  | 'docs'
  | 'changelog'
  | 'sign-in'
  | 'sign-up'
  | 'not-found'

export interface SiteRoute {
  name: SitePageName
  path: string
}

export const SITE_NAV: ReadonlyArray<{ path: string; label: string }> = [
  { path: '/', label: '首页' },
  { path: '/product', label: '产品' },
  { path: '/docs', label: '文档' },
  { path: '/changelog', label: '更新日志' },
  { path: '/about', label: '关于' },
]

/* 认证页面不在官网主导航中，但仍属于官网构建产物。 */
const PAGE_BY_PATH: Readonly<Record<string, SitePageName>> = {
  '/': 'home',
  '/product': 'product',
  '/about': 'about',
  '/docs': 'docs',
  '/changelog': 'changelog',
  '/auth/sign-in': 'sign-in',
  '/auth/sign-up': 'sign-up',
}

export function normalizePath(pathname: string): string {
  if (!pathname) return '/'
  const trimmed = pathname.replace(/\/+$/, '')
  if (trimmed === '') return '/'
  return pathname.endsWith('/') ? trimmed : pathname
}

export function readSiteRoute(pathname: string): SiteRoute {
  const path = normalizePath(pathname)
  return { name: PAGE_BY_PATH[path] ?? 'not-found', path }
}

export function readQueryValue(search: string, key: string): string | null {
  const params = new URLSearchParams(search)
  const value = params.get(key)
  return value && value.trim() ? value : null
}

