const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'
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

export async function fetchAssets() {
  try {
    return await apiGet<any[]>('/assets')
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
