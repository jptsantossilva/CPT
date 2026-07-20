const API_BASE = import.meta.env.VITE_API_BASE || '/api'
export type SyncStatus = {
  status: 'idle' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  started_at?: string | null
  finished_at?: string | null
  last_error?: string | null
  warning?: string | null
  holdings_count?: number | null
  nfts_count?: number | null
  total_eur?: number | null
  total_usd?: number | null
}

export type SyncSchedule = {
  enabled: boolean
  interval_value: number
  interval_unit: 'minutes' | 'hours' | 'days' | 'weeks'
  time_of_day: string
  day_of_week: 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday'
  next_run_at?: string | null
}

export type CurrencySetting = {
  currency: 'EUR' | 'USD'
}

export type PriceSymbolMapping = {
  symbol: string
  provider: string
  provider_id: string
  label?: string | null
  enabled: boolean
  notes?: string | null
  updated_at?: string | null
}

export type SnapshotAnomaly = {
  detected_reasons: string[]
  suggested_reason: string
  eth_quantity: number
}

export type SnapshotAdminRow = {
  id: number
  timestamp: string
  total_eur: number
  total_usd: number
  is_valid: boolean
  invalid_reason?: string | null
  invalidated_at?: string | null
  anomaly?: SnapshotAnomaly | null
}

export type SnapshotAuditResult = {
  scanned: number
  candidate_count: number
  candidates: SnapshotAdminRow[]
}

export type NotificationChannel = 'email' | 'telegram'
export type RecipientType = 'email' | 'telegram_chat'
export type ScheduleMode = 'inherit' | 'custom'

export type NotificationRecipient = {
  id?: number | null
  type: RecipientType
  value: string
  enabled: boolean
}

export type NotificationConfig = {
  id: number
  name: string
  channel: NotificationChannel
  enabled: boolean
  schedule_mode: ScheduleMode
  interval_value: number
  interval_unit: 'minutes' | 'hours' | 'days' | 'weeks'
  time_of_day: string
  day_of_week: 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday'
  timezone: string
  created_at?: string | null
  updated_at?: string | null
  last_sent_at?: string | null
  next_run_at?: string | null
  is_due?: boolean
  recipients: NotificationRecipient[]
}

export type PortfolioHistoryPoint = {
  timestamp: string
  totals: {
    coins_eur: number
    coins_usd: number
    nfts_eur: number
    nfts_usd: number
    portfolio_eur: number
    portfolio_usd: number
  }
  coins: Record<string, { eur: number; usd: number }>
  nfts: Record<string, { eur: number; usd: number }>
}

export type PortfolioHistoryResponse = {
  points: PortfolioHistoryPoint[]
  coin_labels: Record<string, string>
  nft_labels: Record<string, string>
}

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text()
  let data: any = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { detail: text }
    }
  }

  if (!response.ok) {
    const detail = data?.detail || `HTTP ${response.status}`
    throw new Error(String(detail))
  }

  return data as T
}

async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`)
  return parseResponse<T>(response)
}

async function apiPost<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  return parseResponse<T>(response)
}

async function apiPut<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined,
  })
  return parseResponse<T>(response)
}

async function apiDelete<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { method: 'DELETE' })
  return parseResponse<T>(response)
}

export async function fetchLatestSnapshot() {
  try {
    return await apiGet<any>('/snapshot/latest')
  } catch {
    return null
  }
}

export async function fetchAssets(includeHidden = false) {
  try {
    return await apiGet<any[]>(`/assets?include_hidden=${includeHidden ? 'true' : 'false'}`)
  } catch {
    return []
  }
}

export async function fetchNfts(includeHidden = false) {
  try {
    return await apiGet<any[]>(`/nfts?include_hidden=${includeHidden ? 'true' : 'false'}`)
  } catch {
    return []
  }
}

export async function updateNftVisibility(nftId: number, visibility: 'visible' | 'hidden') {
  return apiPut<any>(`/nfts/${nftId}/visibility`, { visibility })
}

export async function fetchAssetIcons(symbols: string[]) {
  if (symbols.length === 0) return {}
  const qs = encodeURIComponent(symbols.join(','))
  return apiGet<Record<string, string>>(`/assets/icons?symbols=${qs}`)
}

export async function listBinanceAccounts() {
  return apiGet<any[]>('/admin/binance-accounts/')
}

export async function createBinanceAccount(payload: any) {
  return apiPost<any>('/admin/binance-accounts/', payload)
}

export async function updateBinanceAccount(accountId: number, payload: any) {
  return apiPut<any>(`/admin/binance-accounts/${accountId}`, payload)
}

export async function deleteBinanceAccount(accountId: number) {
  return apiDelete<any>(`/admin/binance-accounts/${accountId}`)
}

export async function listWallets() {
  return apiGet<any[]>('/admin/wallets/')
}

export async function createWallet(payload: any) {
  return apiPost<any>('/admin/wallets/', payload)
}

export async function updateWallet(walletId: number, payload: any) {
  return apiPut<any>(`/admin/wallets/${walletId}`, payload)
}

export async function deleteWallet(walletId: number) {
  return apiDelete<any>(`/admin/wallets/${walletId}`)
}

export async function syncNow() {
  return apiPost<any>('/sync')
}

export async function fetchSyncStatus() {
  return apiGet<SyncStatus>('/sync/status')
}

export async function fetchSyncSchedule() {
  return apiGet<SyncSchedule>('/admin/sync-schedule/')
}

export async function updateSyncSchedule(payload: Partial<SyncSchedule>) {
  return apiPut<SyncSchedule>('/admin/sync-schedule/', payload)
}

export async function fetchCurrencySetting() {
  return apiGet<CurrencySetting>('/settings/currency')
}

export async function updateCurrencySetting(currency: 'EUR' | 'USD') {
  return apiPut<CurrencySetting>('/settings/currency', { currency })
}

export async function listPriceSymbolMappings() {
  return apiGet<PriceSymbolMapping[]>('/admin/price-mappings/')
}

export async function createPriceSymbolMapping(payload: Partial<PriceSymbolMapping>) {
  return apiPost<PriceSymbolMapping>('/admin/price-mappings/', payload)
}

export async function updatePriceSymbolMapping(symbol: string, payload: Partial<PriceSymbolMapping>) {
  return apiPut<PriceSymbolMapping>(`/admin/price-mappings/${encodeURIComponent(symbol)}`, payload)
}

export async function deletePriceSymbolMapping(symbol: string) {
  return apiDelete<{ status: string }>(`/admin/price-mappings/${encodeURIComponent(symbol)}`)
}

export async function listSnapshotHistory(status: 'all' | 'valid' | 'invalid' = 'all', limit = 500) {
  return apiGet<SnapshotAdminRow[]>(
    `/admin/snapshots/?status=${encodeURIComponent(status)}&limit=${encodeURIComponent(String(limit))}`
  )
}

export async function auditSnapshotHistory() {
  return apiPost<SnapshotAuditResult>('/admin/snapshots/audit')
}

export async function updateSnapshotValidity(snapshotId: number, isValid: boolean, reason?: string | null) {
  return apiPut<SnapshotAdminRow>(`/admin/snapshots/${snapshotId}/validity`, {
    is_valid: isValid,
    reason: reason || null,
  })
}

export async function fetchPortfolioHistory(limit = 800) {
  return apiGet<PortfolioHistoryResponse>(`/history/portfolio?limit=${encodeURIComponent(String(limit))}`)
}

export async function listNotifications() {
  return apiGet<NotificationConfig[]>('/admin/notifications/')
}

export async function createNotification(payload: Partial<NotificationConfig>) {
  return apiPost<NotificationConfig>('/admin/notifications/', payload)
}

export async function updateNotification(notificationId: number, payload: Partial<NotificationConfig>) {
  return apiPut<NotificationConfig>(`/admin/notifications/${notificationId}`, payload)
}

export async function deleteNotification(notificationId: number) {
  return apiDelete<{ status: string }>(`/admin/notifications/${notificationId}`)
}

export async function replaceNotificationRecipients(notificationId: number, recipients: NotificationRecipient[]) {
  return apiPut<NotificationConfig>(`/admin/notifications/${notificationId}/recipients`, { recipients })
}

export async function previewNotification(notificationId: number) {
  return apiGet<any>(`/admin/notifications/${notificationId}/preview`)
}

export async function runNotificationNow(notificationId: number) {
  return apiPost<any>(`/admin/notifications/${notificationId}/run`)
}
