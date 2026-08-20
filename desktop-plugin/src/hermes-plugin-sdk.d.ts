declare module '@hermes/plugin-sdk' {
  import type { ButtonHTMLAttributes, ComponentType, ReactNode } from 'react'

  export interface PluginRestOptions {
    method?: string
    body?: unknown
    headers?: Record<string, string>
  }

  export interface PluginContribution {
    id: string
    area: string
    title?: string
    order?: number
    render?: () => ReactNode
    data?: unknown
  }

  export interface PluginContext {
    readonly source: string
    registerMany: (contributions: PluginContribution[]) => () => void
    rest: <T>(path: string, options?: PluginRestOptions) => Promise<T>
  }

  export interface HermesPlugin {
    id: string
    name?: string
    description?: string
    defaultEnabled?: boolean
    register: (context: PluginContext) => void
  }

  export const ROUTES_AREA: string
  export const SIDEBAR_NAV_AREA: string
  export const STATUSBAR_AREAS: { left: string; right: string }

  export interface QueryOptions<T> {
    queryKey: readonly unknown[]
    queryFn: () => Promise<T>
    refetchInterval?: number
  }

  export function useQuery<T>(options: QueryOptions<T>): {
    data: T | undefined
    error: Error | null
    isLoading: boolean
  }

  export function useQueryClient(): {
    invalidateQueries: (options: { queryKey: readonly unknown[] }) => Promise<void>
  }

  export const Button: ComponentType<ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: 'default' | 'destructive' | 'ghost' | 'outline'
  }>
  export const Badge: ComponentType<{
    children?: ReactNode
    className?: string
    variant?: 'default' | 'muted' | 'warn' | 'destructive' | 'outline'
  }>
  export const EmptyState: ComponentType<{
    title: string
    description?: string
    className?: string
  }>
  export const ConfirmDialog: ComponentType<{
    open: boolean
    onClose: () => void
    onConfirm: () => Promise<void> | void
    title: ReactNode
    description?: ReactNode
    confirmLabel?: string
    destructive?: boolean
  }>
}
