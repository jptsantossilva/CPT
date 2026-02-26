import React from 'react'
import { Box, Button, Card, CardContent, Checkbox, Chip, FormControlLabel, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow, TableSortLabel, TextField, Typography } from '@mui/material'
import { fetchNfts, fetchSyncStatus, updateNftVisibility } from '../shared/api'
import { formatEur, formatUsd } from '../shared/format'

type ChainOption = { key: string; label: string }
type SourceWallet = { id: number; label: string | null; identifier: string | null }
type SortDirection = 'asc' | 'desc'
type SortKey =
  | 'name'
  | 'collection'
  | 'chain'
  | 'token_id'
  | 'wallet'
  | 'valuation_native'
  | 'valuation_eth'
  | 'valuation_eur'
  | 'valuation_usd'
  | 'is_spam'
  | 'has_floor_or_last_sale'
  | 'visibility'

const OPENSEA_FAVICON_URL = 'https://opensea.io/favicon.ico'

function safeNumber(value: unknown): number {
  const n = Number(value || 0)
  return Number.isFinite(n) ? n : 0
}

function safeBool(value: unknown): boolean {
  return value === true || value === 1 || value === '1' || value === 'true'
}

function formatEth(value: number): string {
  return `ETH ${new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 6,
  }).format(value)}`
}

function formatNative(value: number, symbol: string): string {
  return `${symbol || '-'} ${new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 6,
  }).format(value)}`
}

function buildOpenSeaItemUrl(chain: string, contract: string, tokenId: string): string | null {
  const chainKey = String(chain || '').trim().toLowerCase()
  const contractKey = String(contract || '').trim().toLowerCase()
  const tokenKey = String(tokenId || '').trim()
  if (!chainKey || !contractKey || !tokenKey) return null
  const openseaChain = chainKey === 'polygon' ? 'matic' : chainKey
  return `https://opensea.io/item/${openseaChain}/${contractKey}/${tokenKey}`
}

function walletDisplay(row: any): string {
  return String(row.account_label || row.account_identifier || row.owner || '-')
}

function compareRows(a: any, b: any, key: SortKey): number {
  const str = (v: unknown) => String(v || '').toLowerCase()
  const num = (v: unknown) => safeNumber(v)
  const boolNum = (v: unknown) => (safeBool(v) ? 1 : 0)

  switch (key) {
    case 'name':
      return str(a.name).localeCompare(str(b.name))
    case 'collection':
      return str(a.collection).localeCompare(str(b.collection))
    case 'chain':
      return str(a.chain).localeCompare(str(b.chain))
    case 'token_id': {
      const aN = Number(a.token_id)
      const bN = Number(b.token_id)
      const aNum = Number.isFinite(aN)
      const bNum = Number.isFinite(bN)
      if (aNum && bNum) return aN - bN
      return str(a.token_id).localeCompare(str(b.token_id))
    }
    case 'wallet':
      return walletDisplay(a).toLowerCase().localeCompare(walletDisplay(b).toLowerCase())
    case 'valuation_native':
      return num(a.valuation_native) - num(b.valuation_native)
    case 'valuation_eth':
      return num(a.valuation_eth) - num(b.valuation_eth)
    case 'valuation_eur':
      return num(a.valuation_eur) - num(b.valuation_eur)
    case 'valuation_usd':
      return num(a.valuation_usd) - num(b.valuation_usd)
    case 'is_spam':
      return boolNum(a.is_spam) - boolNum(b.is_spam)
    case 'has_floor_or_last_sale':
      return boolNum(a.has_floor_or_last_sale) - boolNum(b.has_floor_or_last_sale)
    case 'visibility':
      return str(a.visibility).localeCompare(str(b.visibility))
    default:
      return 0
  }
}

export default function Nfts() {
  const [rows, setRows] = React.useState<any[]>([])
  const [search, setSearch] = React.useState('')
  const [selectedWalletIds, setSelectedWalletIds] = React.useState<number[]>([])
  const [selectedChains, setSelectedChains] = React.useState<string[]>([])
  const [hideLowValue, setHideLowValue] = React.useState(true)
  const [spamFilter, setSpamFilter] = React.useState<'all' | 'spam' | 'not_spam'>('not_spam')
  const [floorSaleFilter, setFloorSaleFilter] = React.useState<'all' | 'yes' | 'no'>('yes')
  const [visibilityFilter, setVisibilityFilter] = React.useState<'all' | 'visible' | 'hidden'>('visible')
  const [faviconFailed, setFaviconFailed] = React.useState(false)
  const [sortKey, setSortKey] = React.useState<SortKey>('valuation_usd')
  const [sortDirection, setSortDirection] = React.useState<SortDirection>('desc')
  const [savingVisibilityIds, setSavingVisibilityIds] = React.useState<number[]>([])
  const lastSyncFinishedRef = React.useRef<string | null>(null)

  const load = React.useCallback(async () => {
    try {
      const data = await fetchNfts(true)
      setRows(data || [])
    } catch {
      setRows([])
    }
  }, [])

  React.useEffect(() => {
    load()
  }, [load])

  React.useEffect(() => {
    let mounted = true
    const poll = window.setInterval(async () => {
      try {
        const status = await fetchSyncStatus()
        if (!mounted) return
        const finishedAt = status.finished_at || null
        if (status.status === 'completed' && finishedAt && finishedAt !== lastSyncFinishedRef.current) {
          lastSyncFinishedRef.current = finishedAt
          load()
        }
      } catch {
        // ignore transient polling errors
      }
    }, 1500)

    return () => {
      mounted = false
      window.clearInterval(poll)
    }
  }, [load])

  const chainOptions = React.useMemo<ChainOption[]>(() => {
    const keys = new Set<string>()
    for (const row of rows) {
      const key = String(row.chain || '').trim().toLowerCase()
      if (key) keys.add(key)
    }
    return Array.from(keys)
      .sort((a, b) => a.localeCompare(b))
      .map((key) => ({ key, label: key.toUpperCase() }))
  }, [rows])

  const walletOptions = React.useMemo<SourceWallet[]>(() => {
    const map = new Map<number, SourceWallet>()
    for (const row of rows) {
      const id = Number(row.account_id || 0)
      if (!id) continue
      if (!map.has(id)) {
        map.set(id, {
          id,
          label: row.account_label || null,
          identifier: row.account_identifier || null,
        })
      }
    }
    return Array.from(map.values()).sort((a, b) => {
      const aLabel = a.label || a.identifier || ''
      const bLabel = b.label || b.identifier || ''
      return aLabel.localeCompare(bLabel) || a.id - b.id
    })
  }, [rows])

  React.useEffect(() => {
    if (chainOptions.length === 0) {
      setSelectedChains([])
      return
    }
    setSelectedChains((prev) => {
      if (prev.length === 0) return chainOptions.map((c) => c.key)
      const valid = prev.filter((key) => chainOptions.some((c) => c.key === key))
      return valid.length > 0 ? valid : chainOptions.map((c) => c.key)
    })
  }, [chainOptions])

  React.useEffect(() => {
    if (walletOptions.length === 0) {
      setSelectedWalletIds([])
      return
    }
    setSelectedWalletIds((prev) => {
      if (prev.length === 0) return walletOptions.map((w) => w.id)
      const valid = prev.filter((id) => walletOptions.some((w) => w.id === id))
      return valid.length > 0 ? valid : walletOptions.map((w) => w.id)
    })
  }, [walletOptions])

  function toggleChain(key: string) {
    setSelectedChains((prev) => {
      if (prev.includes(key)) {
        const next = prev.filter((item) => item !== key)
        return next.length > 0 ? next : prev
      }
      return [...prev, key]
    })
  }

  function toggleWallet(id: number) {
    setSelectedWalletIds((prev) => {
      if (prev.includes(id)) {
        const next = prev.filter((item) => item !== id)
        return next.length > 0 ? next : prev
      }
      return [...prev, id]
    })
  }

  const filtered = React.useMemo(() => {
    const query = search.trim().toLowerCase()
    return rows.filter((row) => {
      const chain = String(row.chain || '').trim().toLowerCase()
      if (selectedChains.length > 0 && !selectedChains.includes(chain)) return false
      if (selectedWalletIds.length > 0 && !selectedWalletIds.includes(Number(row.account_id || 0))) return false
      const isSpam = safeBool(row.is_spam)
      const hasFloorOrLastSale = safeBool(row.has_floor_or_last_sale)
      const visibility = String(row.visibility || 'visible').toLowerCase()
      if (spamFilter === 'spam' && !isSpam) return false
      if (spamFilter === 'not_spam' && isSpam) return false
      if (floorSaleFilter === 'yes' && !hasFloorOrLastSale) return false
      if (floorSaleFilter === 'no' && hasFloorOrLastSale) return false
      if (visibilityFilter !== 'all' && visibility !== visibilityFilter) return false
      if (hideLowValue && safeNumber(row.valuation_usd) <= 1) return false
      if (!query) return true
      const haystack = [
        row.name,
        row.collection,
        row.contract,
        row.token_id,
        row.owner,
      ]
        .map((x) => String(x || '').toLowerCase())
        .join(' ')
      return haystack.includes(query)
    })
  }, [rows, search, selectedChains, selectedWalletIds, hideLowValue, spamFilter, floorSaleFilter, visibilityFilter])

  const sorted = React.useMemo(() => {
    const dir = sortDirection === 'asc' ? 1 : -1
    return [...filtered]
      .map((row, idx) => ({ row, idx }))
      .sort((a, b) => {
        const diff = compareRows(a.row, b.row, sortKey) * dir
        if (diff !== 0) return diff
        return a.idx - b.idx
      })
      .map((item) => item.row)
  }, [filtered, sortDirection, sortKey])

  function onSort(column: SortKey) {
    if (sortKey === column) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortKey(column)
    setSortDirection('asc')
  }

  async function toggleVisibility(row: any) {
    const id = Number(row.id || 0)
    if (!id) return
    const current = String(row.visibility || 'visible').toLowerCase() === 'hidden' ? 'hidden' : 'visible'
    const next = current === 'hidden' ? 'visible' : 'hidden'
    setSavingVisibilityIds((prev) => [...prev, id])
    try {
      await updateNftVisibility(id, next)
      setRows((prev) =>
        prev.map((item) => (Number(item.id || 0) === id ? { ...item, visibility: next } : item))
      )
    } finally {
      setSavingVisibilityIds((prev) => prev.filter((x) => x !== id))
    }
  }

  function exportCsv() {
    const headers = [
      'Name',
      'Collection',
      'Chain',
      'Token ID',
      'Wallet',
      'Value Native',
      'Value ETH',
      'Value EUR',
      'Value USD',
      'is_spam',
      'has_floor_or_last_sale',
      'visibility',
      'Contract',
      'OpenSea URL',
    ]
    const escapeCsv = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`
    const lines = sorted.map((row) => {
      const openSeaUrl = buildOpenSeaItemUrl(String(row.chain || ''), String(row.contract || ''), String(row.token_id || '')) || ''
      return [
        row.name || '',
        row.collection || '',
        row.chain ? String(row.chain).toUpperCase() : '',
        row.token_id || '',
        row.account_label || row.account_identifier || row.owner || '',
        formatNative(safeNumber(row.valuation_native), String(row.valuation_symbol || '-')),
        row.valuation_eth == null ? '' : formatEth(safeNumber(row.valuation_eth)),
        formatEur(safeNumber(row.valuation_eur)),
        formatUsd(safeNumber(row.valuation_usd)),
        safeBool(row.is_spam),
        safeBool(row.has_floor_or_last_sale),
        String(row.visibility || 'visible'),
        row.contract || '',
        openSeaUrl,
      ].map(escapeCsv).join(',')
    })

    const csv = [headers.map(escapeCsv).join(','), ...lines].join('\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `nfts_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  function exportPdf() {
    const win = window.open('', '_blank')
    if (!win) return
    const rowsHtml = sorted
      .map((row) => {
        return `<tr>
<td>${String(row.name || '-')}</td>
<td>${String(row.collection || '-')}</td>
<td>${String(row.chain ? String(row.chain).toUpperCase() : '-')}</td>
<td>${String(row.token_id || '-')}</td>
<td>${String(row.account_label || row.account_identifier || row.owner || '-')}</td>
<td>${String(formatNative(safeNumber(row.valuation_native), String(row.valuation_symbol || '-')))}</td>
<td>${String(row.valuation_eth == null ? '-' : formatEth(safeNumber(row.valuation_eth)))}</td>
<td>${String(formatEur(safeNumber(row.valuation_eur)))}</td>
<td>${String(formatUsd(safeNumber(row.valuation_usd)))}</td>
<td>${String(safeBool(row.is_spam))}</td>
<td>${String(safeBool(row.has_floor_or_last_sale))}</td>
<td>${String(row.visibility || 'visible')}</td>
</tr>`
      })
      .join('')

    win.document.write(`<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>NFTs Export</title>
<style>
body { font-family: Arial, sans-serif; margin: 16px; }
h2 { margin: 0 0 12px; }
table { border-collapse: collapse; width: 100%; font-size: 12px; }
th, td { border: 1px solid #ccc; padding: 6px 8px; text-align: left; }
th { background: #f2f2f2; }
</style>
</head>
<body>
<h2>NFTs Export</h2>
<table>
<thead>
<tr>
<th>Name</th><th>Collection</th><th>Chain</th><th>Token ID</th><th>Wallet</th>
<th>Value Native</th><th>Value ETH</th><th>Value EUR</th><th>Value USD</th>
<th>is_spam</th><th>has_floor_or_last_sale</th><th>visibility</th>
</tr>
</thead>
<tbody>${rowsHtml}</tbody>
</table>
</body>
</html>`)
    win.document.close()
    win.focus()
    win.print()
  }

  const totals = React.useMemo(
    () =>
      sorted.reduce(
        (acc, row) => {
          acc.eur += safeNumber(row.valuation_eur)
          acc.usd += safeNumber(row.valuation_usd)
          return acc
        },
        { eur: 0, usd: 0 }
      ),
    [sorted]
  )

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1.5}>
            <Typography variant="h5">NFTs</Typography>
            <TextField
              size="small"
              label="Search NFT"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              sx={{ minWidth: 240 }}
            />
          </Stack>

          <Stack
            direction={{ xs: 'column', md: 'row' }}
            spacing={2}
            alignItems={{ xs: 'flex-start', md: 'center' }}
            justifyContent="space-between"
          >
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <Typography variant="subtitle1">
                Total EUR: <strong>{formatEur(totals.eur, { withCode: false })}</strong>
              </Typography>
              <Typography variant="subtitle1">
                Total USD: <strong>{formatUsd(totals.usd, { withCode: false })}</strong>
              </Typography>
            </Stack>
            <FormControlLabel
              control={<Checkbox checked={hideLowValue} onChange={(e) => setHideLowValue(e.target.checked)} />}
              label={<Typography variant="body2">Hide assets with value &lt;= 1 USD</Typography>}
              sx={{ mr: 0 }}
            />
          </Stack>

          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            <Typography variant="body2" color="text.secondary">Wallets:</Typography>
            {walletOptions.map((wallet) => {
              const selected = selectedWalletIds.includes(wallet.id)
              return (
                <Chip
                  key={wallet.id}
                  label={wallet.label || wallet.identifier || 'unknown'}
                  color={selected ? 'primary' : 'default'}
                  variant={selected ? 'filled' : 'outlined'}
                  onClick={() => toggleWallet(wallet.id)}
                />
              )
            })}
          </Stack>

          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            <Typography variant="body2" color="text.secondary">Chains:</Typography>
            {chainOptions.map((chain) => {
              const selected = selectedChains.includes(chain.key)
              return (
                <Chip
                  key={chain.key}
                  label={chain.label}
                  color={selected ? 'primary' : 'default'}
                  variant={selected ? 'filled' : 'outlined'}
                  onClick={() => toggleChain(chain.key)}
                />
              )
            })}
          </Stack>

          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            <Typography variant="body2" color="text.secondary">Spam:</Typography>
            {[
              { key: 'all', label: 'All' },
              { key: 'spam', label: 'Only spam' },
              { key: 'not_spam', label: 'Only non-spam' },
            ].map((opt) => (
              <Chip
                key={opt.key}
                label={opt.label}
                color={spamFilter === opt.key ? 'primary' : 'default'}
                variant={spamFilter === opt.key ? 'filled' : 'outlined'}
                onClick={() => setSpamFilter(opt.key as 'all' | 'spam' | 'not_spam')}
              />
            ))}
          </Stack>

          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            <Typography variant="body2" color="text.secondary">Floor/Last Sale:</Typography>
            {[
              { key: 'all', label: 'All' },
              { key: 'yes', label: 'Has floor/sale' },
              { key: 'no', label: 'No floor/sale' },
            ].map((opt) => (
              <Chip
                key={opt.key}
                label={opt.label}
                color={floorSaleFilter === opt.key ? 'primary' : 'default'}
                variant={floorSaleFilter === opt.key ? 'filled' : 'outlined'}
                onClick={() => setFloorSaleFilter(opt.key as 'all' | 'yes' | 'no')}
              />
            ))}
          </Stack>

          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            <Typography variant="body2" color="text.secondary">Visibility:</Typography>
            {[
              { key: 'all', label: 'All' },
              { key: 'visible', label: 'Visible' },
              { key: 'hidden', label: 'Hidden' },
            ].map((opt) => (
              <Chip
                key={opt.key}
                label={opt.label}
                color={visibilityFilter === opt.key ? 'primary' : 'default'}
                variant={visibilityFilter === opt.key ? 'filled' : 'outlined'}
                onClick={() => setVisibilityFilter(opt.key as 'all' | 'visible' | 'hidden')}
              />
            ))}
          </Stack>

          <Stack direction="row" spacing={1} justifyContent="space-between" alignItems="center">
            <Typography variant="body2" color="text.secondary">
              Results: {sorted.length}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button variant="outlined" size="small" onClick={exportCsv}>Export CSV</Button>
              <Button variant="outlined" size="small" onClick={exportPdf}>Export PDF</Button>
            </Stack>
          </Stack>

          <Box sx={{ overflowX: 'auto' }}>
            <Table
              size="small"
              sx={{
                minWidth: 1300,
                '& th, & td': { whiteSpace: 'nowrap' },
              }}
            >
              <TableHead>
                <TableRow>
                  <TableCell sx={{ width: 56 }} />
                  <TableCell sortDirection={sortKey === 'name' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'name'} direction={sortKey === 'name' ? sortDirection : 'asc'} onClick={() => onSort('name')}>
                      Name
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'collection' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'collection'} direction={sortKey === 'collection' ? sortDirection : 'asc'} onClick={() => onSort('collection')}>
                      Collection
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'chain' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'chain'} direction={sortKey === 'chain' ? sortDirection : 'asc'} onClick={() => onSort('chain')}>
                      Chain
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'token_id' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'token_id'} direction={sortKey === 'token_id' ? sortDirection : 'asc'} onClick={() => onSort('token_id')}>
                      Token ID
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'wallet' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'wallet'} direction={sortKey === 'wallet' ? sortDirection : 'asc'} onClick={() => onSort('wallet')}>
                      Wallet
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'valuation_native' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'valuation_native'} direction={sortKey === 'valuation_native' ? sortDirection : 'asc'} onClick={() => onSort('valuation_native')}>
                      Value Native
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'valuation_eth' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'valuation_eth'} direction={sortKey === 'valuation_eth' ? sortDirection : 'asc'} onClick={() => onSort('valuation_eth')}>
                      Value ETH
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'valuation_eur' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'valuation_eur'} direction={sortKey === 'valuation_eur' ? sortDirection : 'asc'} onClick={() => onSort('valuation_eur')}>
                      Value EUR
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'valuation_usd' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'valuation_usd'} direction={sortKey === 'valuation_usd' ? sortDirection : 'asc'} onClick={() => onSort('valuation_usd')}>
                      Value USD
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'is_spam' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'is_spam'} direction={sortKey === 'is_spam' ? sortDirection : 'asc'} onClick={() => onSort('is_spam')}>
                      Spam
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'has_floor_or_last_sale' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'has_floor_or_last_sale'} direction={sortKey === 'has_floor_or_last_sale' ? sortDirection : 'asc'} onClick={() => onSort('has_floor_or_last_sale')}>
                      Has Floor / Last Sale
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortKey === 'visibility' ? sortDirection : false}>
                    <TableSortLabel active={sortKey === 'visibility'} direction={sortKey === 'visibility' ? sortDirection : 'asc'} onClick={() => onSort('visibility')}>
                      Visibility
                    </TableSortLabel>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sorted.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={13}>
                      <Typography color="text.secondary">No NFTs found.</Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
                {sorted.map((row, idx) => (
                  <TableRow
                    key={`${row.chain}-${row.contract}-${row.token_id}-${idx}`}
                    sx={(theme) => ({
                      backgroundColor:
                        idx % 2 === 0
                          ? 'transparent'
                          : theme.palette.mode === 'dark'
                            ? 'rgba(255,255,255,0.03)'
                            : 'rgba(0,0,0,0.02)',
                      transition: 'background-color 120ms ease',
                      '&:hover': {
                        backgroundColor:
                          theme.palette.mode === 'dark'
                            ? 'rgba(91,141,239,0.18)'
                            : 'rgba(91,141,239,0.12)',
                      },
                    })}
                  >
                    <TableCell>
                      {buildOpenSeaItemUrl(String(row.chain || ''), String(row.contract || ''), String(row.token_id || '')) ? (
                        <Link
                          href={buildOpenSeaItemUrl(String(row.chain || ''), String(row.contract || ''), String(row.token_id || '')) || undefined}
                          target="_blank"
                          rel="noopener noreferrer"
                          underline="none"
                          aria-label="Open NFT on OpenSea"
                          sx={{ display: 'inline-flex', alignItems: 'center' }}
                        >
                          {!faviconFailed ? (
                            <Box
                              component="img"
                              src={OPENSEA_FAVICON_URL}
                              alt="OpenSea"
                              onError={() => setFaviconFailed(true)}
                              sx={{ width: 20, height: 20, borderRadius: '50%' }}
                            />
                          ) : (
                            <Box
                              component="span"
                              sx={{
                                width: 20,
                                height: 20,
                                borderRadius: '50%',
                                display: 'inline-grid',
                                placeItems: 'center',
                                bgcolor: '#2081e2',
                                color: '#fff',
                                fontSize: 10,
                                fontWeight: 700,
                                lineHeight: 1,
                              }}
                            >
                              OS
                            </Box>
                          )}
                        </Link>
                      ) : '-'}
                    </TableCell>
                    <TableCell>{row.name || '-'}</TableCell>
                    <TableCell>{row.collection || '-'}</TableCell>
                    <TableCell>{row.chain ? String(row.chain).toUpperCase() : '-'}</TableCell>
                    <TableCell>{row.token_id || '-'}</TableCell>
                    <TableCell
                      sx={
                        row.account_label
                          ? undefined
                          : { fontFamily: 'monospace' }
                      }
                    >
                      {walletDisplay(row)}
                    </TableCell>
                    <TableCell>{formatNative(safeNumber(row.valuation_native), String(row.valuation_symbol || '-'))}</TableCell>
                    <TableCell>
                      {row.valuation_eth == null ? '-' : formatEth(safeNumber(row.valuation_eth))}
                    </TableCell>
                    <TableCell>{formatEur(safeNumber(row.valuation_eur))}</TableCell>
                    <TableCell>{formatUsd(safeNumber(row.valuation_usd))}</TableCell>
                    <TableCell>{String(safeBool(row.is_spam))}</TableCell>
                    <TableCell>{String(safeBool(row.has_floor_or_last_sale))}</TableCell>
                    <TableCell>
                      <Chip
                        label={String(row.visibility || 'visible').toLowerCase() === 'hidden' ? 'Hidden' : 'Visible'}
                        size="small"
                        color={String(row.visibility || 'visible').toLowerCase() === 'hidden' ? 'default' : 'primary'}
                        variant={String(row.visibility || 'visible').toLowerCase() === 'hidden' ? 'outlined' : 'filled'}
                        onClick={() => toggleVisibility(row)}
                        disabled={savingVisibilityIds.includes(Number(row.id || 0))}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Stack>
      </CardContent>
    </Card>
  )
}
