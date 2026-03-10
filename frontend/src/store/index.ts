import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  createPlaygroundSlice,
  type PlaygroundSlice,
} from './slices/playgroundSlice'
import {
  createAnalyticsSlice,
  type AnalyticsSlice,
} from './slices/analyticsSlice'
import {
  createRequestsSlice,
  type RequestsSlice,
} from './slices/requestsSlice'
import { createKbSlice, type KbSlice } from './slices/kbSlice'
import { createPolicySlice, type PolicySlice } from './slices/policySlice'

export type AppStore = PlaygroundSlice &
  AnalyticsSlice &
  RequestsSlice &
  KbSlice &
  PolicySlice

export const useAppStore = create<AppStore>()(
  devtools(
    (...args) => ({
      ...createPlaygroundSlice(...args),
      ...createAnalyticsSlice(...args),
      ...createRequestsSlice(...args),
      ...createKbSlice(...args),
      ...createPolicySlice(...args),
    }),
    { name: 'SentinelStore' },
  ),
)
