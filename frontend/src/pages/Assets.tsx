import React from 'react'
import { Box, Card, CardContent, Checkbox, Chip, FormControlLabel, Stack, Table, TableBody, TableCell, TableHead, TableRow, TableSortLabel, TextField, Tooltip, Typography } from '@mui/material'
import { fetchAssetIcons, fetchAssets } from '../shared/api'
import { formatEur, formatUsd } from '../shared/format'

type SortField = 'asset_symbol' | 'account' | 'chain' | 'quantity' | 'unit_price' | 'value_eur' | 'value_usd'
type SortDir = 'asc' | 'desc'
type SourceAccount = { id: number; label: string | null; identifier: string | null }
type SourceChain = { key: string; label: string }
const ICON_SYMBOL_ALIASES: Record<string, string[]> = {
  GUN: ['gunz', 'gun'],
  GPS: ['goplus-security', 'goplus', 'gps'],
}

function formatUnitPrice(price: number, currency: 'EUR' | 'USD', valueEur: number, valueUsd: number) {
  if (price <= 0) return '-'
  const hasPositiveValue = valueEur > 0 || valueUsd > 0
  const rounded2 = Number(price.toFixed(2))
  const decimals = hasPositiveValue && rounded2 === 0 ? 8 : 2
  if (currency === 'USD') {
    return formatUsd(price, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  }
  return formatEur(price, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
}

function accountDisplay(a: any): string {
  return String(a.account_label || a.account_identifier || a.account_display || '-')
}

function unitPriceSortValue(a: any): number {
  const usd = Number(a.price_usd || 0)
  if (usd > 0) return usd
  const eur = Number(a.price_eur || 0)
  if (eur > 0) return eur
  return 0
}

function shortContract(value: unknown): string {
  const contract = String(value || '')
  if (contract.length <= 18) return contract
  return `${contract.slice(0, 10)}…${contract.slice(-6)}`
}

function AssetIcon({ symbol, iconUrl, size = 18 }: { symbol: string; iconUrl?: string; size?: number }) {
  const normalized = symbol.toLowerCase()
  const aliases = ICON_SYMBOL_ALIASES[symbol.toUpperCase()] || []
  const sources = React.useMemo(
    () => {
      const fallbackSources = [normalized, ...aliases].flatMap((token) => [
        `https://cdn.jsdelivr.net/gh/spothq/cryptocurrency-icons@master/128/color/${token}.png`,
        `https://assets.coincap.io/assets/icons/${token}@2x.png`,
      ])
      return iconUrl ? [iconUrl, ...fallbackSources] : fallbackSources
    },
    [aliases, iconUrl, normalized]
  )
  const [sourceIndex, setSourceIndex] = React.useState(0)
  const src = sources[sourceIndex]

  React.useEffect(() => {
    setSourceIndex(0)
  }, [normalized, iconUrl])

  if (!src || symbol === 'Other') {
    return (
      <Box
        component="span"
        sx={{
          width: size,
          height: size,
          borderRadius: '50%',
          display: 'inline-grid',
          placeItems: 'center',
          bgcolor: 'action.hover',
          fontSize: Math.max(9, Math.floor(size * 0.48)),
          fontWeight: 700,
          textTransform: 'uppercase',
        }}
      >
        {symbol.slice(0, 1)}
      </Box>
    )
  }

  return (
    <Box
      component="img"
      src={src}
      alt={`${symbol} icon`}
      loading="lazy"
      onError={() => {
        if (sourceIndex < sources.length - 1) {
          setSourceIndex((idx) => idx + 1)
        } else {
          setSourceIndex(sources.length)
        }
      }}
      sx={{
        width: size,
        height: size,
        borderRadius: '50%',
        objectFit: 'cover',
        bgcolor: 'common.white',
        boxShadow: '0 0 0 1px rgba(128, 128, 128, 0.18)',
      }}
    />
  )
}

export default function Assets() {
  const [assets, setAssets] = React.useState<any[]>([])
  const [assetIcons, setAssetIcons] = React.useState<Record<string, string>>({})
  const [search, setSearch] = React.useState('')
  const [sortBy, setSortBy] = React.useState<SortField>('value_usd')
  const [sortDir, setSortDir] = React.useState<SortDir>('desc')
  const [selectedAccountIds, setSelectedAccountIds] = React.useState<number[]>([])
  const [selectedChains, setSelectedChains] = React.useState<string[]>([])
  const [hideLowValue, setHideLowValue] = React.useState(true)
  const [showSuspicious, setShowSuspicious] = React.useState(false)

  React.useEffect(() => {
    fetchAssets(showSuspicious).then(setAssets).catch(() => {})
  }, [showSuspicious])

  React.useEffect(() => {
    const symbols = Array.from(new Set(
      assets
        .filter((a) => String(a.visibility || 'visible').toLowerCase() !== 'hidden')
        .map((a) => String(a.asset_symbol || '').toUpperCase())
        .filter(Boolean)
    ))
    if (symbols.length === 0) {
      setAssetIcons({})
      return
    }
    fetchAssetIcons(symbols)
      .then((icons) => setAssetIcons(icons || {}))
      .catch(() => setAssetIcons({}))
  }, [assets])

  const sourceOptions = React.useMemo<SourceAccount[]>(() => {
    const map = new Map<number, SourceAccount>()
    for (const asset of assets) {
      const id = Number(asset.account_id || 0)
      if (!id) continue
      if (!map.has(id)) {
        map.set(id, { id, label: asset.account_label || null, identifier: asset.account_identifier || null })
      }
    }
    return Array.from(map.values()).sort((a, b) => {
      const aLabel = a.label || a.identifier || ''
      const bLabel = b.label || b.identifier || ''
      return aLabel.localeCompare(bLabel) || a.id - b.id
    })
  }, [assets])

  const chainOptions = React.useMemo<SourceChain[]>(() => {
    const map = new Map<string, SourceChain>()
    for (const asset of assets) {
      const key = String(asset.chain || '').trim().toLowerCase() || 'no-chain'
      if (!map.has(key)) {
        map.set(key, { key, label: key === 'no-chain' ? 'No chain' : key.toUpperCase() })
      }
    }
    return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label))
  }, [assets])

  React.useEffect(() => {
    if (sourceOptions.length === 0) {
      setSelectedAccountIds([])
      return
    }
    setSelectedAccountIds((prev) => {
      if (prev.length === 0) return sourceOptions.map((o) => o.id)
      const valid = prev.filter((id) => sourceOptions.some((o) => o.id === id))
      return valid.length > 0 ? valid : sourceOptions.map((o) => o.id)
    })
  }, [sourceOptions])

  React.useEffect(() => {
    if (chainOptions.length === 0) {
      setSelectedChains([])
      return
    }
    setSelectedChains((prev) => {
      if (prev.length === 0) return chainOptions.map((o) => o.key)
      const valid = prev.filter((key) => chainOptions.some((o) => o.key === key))
      return valid.length > 0 ? valid : chainOptions.map((o) => o.key)
    })
  }, [chainOptions])

  function onSort(field: SortField) {
    if (sortBy === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortBy(field)
    setSortDir(['value_eur', 'value_usd', 'quantity', 'unit_price'].includes(field) ? 'desc' : 'asc')
  }

  function toggleAccount(id: number) {
    setSelectedAccountIds((prev) => {
      if (prev.includes(id)) {
        const next = prev.filter((item) => item !== id)
        return next.length > 0 ? next : prev
      }
      return [...prev, id]
    })
  }

  function toggleChain(key: string) {
    setSelectedChains((prev) => {
      if (prev.includes(key)) {
        const next = prev.filter((item) => item !== key)
        return next.length > 0 ? next : prev
      }
      return [...prev, key]
    })
  }

  const filtered = assets.filter((a) => {
    const query = search.trim().toLowerCase()
    const nameOk = String(a.asset_symbol || '').toLowerCase().includes(query)
      || String(a.contract_address || '').toLowerCase().includes(query)
    if (!nameOk) return false
    const hidden = String(a.visibility || 'visible').toLowerCase() === 'hidden'
    if (hideLowValue && !hidden && Number(a.value_usd || 0) <= 1) return false
    if (selectedAccountIds.length > 0 && !selectedAccountIds.includes(Number(a.account_id || 0))) return false
    const chainKey = String(a.chain || '').trim().toLowerCase() || 'no-chain'
    if (selectedChains.length > 0 && !selectedChains.includes(chainKey)) return false
    return true
  })

  const sorted = [...filtered].sort((a, b) => {
    const dir = sortDir === 'asc' ? 1 : -1
    let diff = 0
    switch (sortBy) {
      case 'asset_symbol':
        diff = String(a.asset_symbol || '').localeCompare(String(b.asset_symbol || ''))
        break
      case 'account':
        diff = accountDisplay(a).localeCompare(accountDisplay(b))
        break
      case 'chain':
        diff = String(a.chain || '').localeCompare(String(b.chain || ''))
        break
      case 'quantity':
        diff = Number(a.quantity || 0) - Number(b.quantity || 0)
        break
      case 'unit_price':
        diff = unitPriceSortValue(a) - unitPriceSortValue(b)
        break
      case 'value_eur':
        diff = Number(a.value_eur || 0) - Number(b.value_eur || 0)
        break
      case 'value_usd':
        diff = Number(a.value_usd || 0) - Number(b.value_usd || 0)
        break
      default:
        diff = 0
        break
    }
    return diff * dir
  })
  const totals = React.useMemo(() => {
    return filtered.reduce(
      (acc, row) => {
        if (String(row.visibility || 'visible').toLowerCase() === 'hidden') return acc
        acc.eur += Number(row.value_eur || 0)
        acc.usd += Number(row.value_usd || 0)
        return acc
      },
      { eur: 0, usd: 0 }
    )
  }, [filtered])

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }} spacing={1.5}>
            <Typography variant="h5">Coins</Typography>
            <Stack direction="column" spacing={0.5} alignItems={{ xs: 'flex-start', md: 'flex-end' }}>
              <TextField
                size="small"
                label="Search coin"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                sx={{ minWidth: 240 }}
              />
            </Stack>
          </Stack>

          <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems={{ xs: 'flex-start', md: 'center' }} justifyContent="space-between">
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
              <Typography variant="subtitle1">
                Total EUR: <strong>{formatEur(totals.eur, { withCode: false })}</strong>
              </Typography>
              <Typography variant="subtitle1">
                Total USD: <strong>{formatUsd(totals.usd, { withCode: false })}</strong>
              </Typography>
            </Stack>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
              <FormControlLabel
                control={<Checkbox checked={hideLowValue} onChange={(e) => setHideLowValue(e.target.checked)} />}
                label={<Typography variant="body2">Hide coins with value &lt;= 1 USD</Typography>}
              />
              <FormControlLabel
                control={<Checkbox checked={showSuspicious} onChange={(e) => setShowSuspicious(e.target.checked)} />}
                label={<Typography variant="body2">Show suspicious tokens</Typography>}
              />
            </Stack>
          </Stack>

          <Stack direction="row" gap={1} flexWrap="wrap" alignItems="center">
            <Typography variant="body2" color="text.secondary">Exchanges and Wallets:</Typography>
            {sourceOptions.map((source) => {
              const selected = selectedAccountIds.includes(source.id)
              return (
                <Chip
                  key={source.id}
                  label={source.label || source.identifier || 'unknown'}
                  color={selected ? 'primary' : 'default'}
                  variant={selected ? 'filled' : 'outlined'}
                  onClick={() => toggleAccount(source.id)}
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

          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sortDirection={sortBy === 'asset_symbol' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'asset_symbol'}
                      direction={sortBy === 'asset_symbol' ? sortDir : 'asc'}
                      onClick={() => onSort('asset_symbol')}
                    >
                      Coin
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'account' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'account'}
                      direction={sortBy === 'account' ? sortDir : 'asc'}
                      onClick={() => onSort('account')}
                    >
                      Account
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'chain' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'chain'}
                      direction={sortBy === 'chain' ? sortDir : 'asc'}
                      onClick={() => onSort('chain')}
                    >
                      Chain
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'quantity' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'quantity'}
                      direction={sortBy === 'quantity' ? sortDir : 'asc'}
                      onClick={() => onSort('quantity')}
                    >
                      Quantity
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'unit_price' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'unit_price'}
                      direction={sortBy === 'unit_price' ? sortDir : 'asc'}
                      onClick={() => onSort('unit_price')}
                    >
                      Unit Price
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'value_eur' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'value_eur'}
                      direction={sortBy === 'value_eur' ? sortDir : 'asc'}
                      onClick={() => onSort('value_eur')}
                    >
                      Value EUR
                    </TableSortLabel>
                  </TableCell>
                  <TableCell sortDirection={sortBy === 'value_usd' ? sortDir : false}>
                    <TableSortLabel
                      active={sortBy === 'value_usd'}
                      direction={sortBy === 'value_usd' ? sortDir : 'asc'}
                      onClick={() => onSort('value_usd')}
                    >
                      Value USD
                    </TableSortLabel>
                  </TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sorted.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7}>
                      <Typography color="text.secondary">No coins to display.</Typography>
                    </TableCell>
                  </TableRow>
                ) : null}
                {sorted.map((a, idx) => (
                  <TableRow
                    key={`${a.asset_key || a.asset_symbol}-${a.account_id}`}
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
                      <Stack direction="row" spacing={1} alignItems="flex-start">
                        {String(a.visibility || 'visible').toLowerCase() === 'hidden' ? (
                          <Box
                            component="span"
                            sx={{
                              mt: 0.25,
                              width: 18,
                              height: 18,
                              borderRadius: '50%',
                              display: 'inline-grid',
                              placeItems: 'center',
                              bgcolor: 'warning.main',
                              color: 'warning.contrastText',
                              fontSize: 12,
                              fontWeight: 800,
                            }}
                          >
                            !
                          </Box>
                        ) : (
                          <AssetIcon symbol={String(a.asset_symbol || '')} iconUrl={assetIcons[String(a.asset_symbol || '').toUpperCase()]} />
                        )}
                        <Stack spacing={0.25}>
                          <span>{a.asset_symbol}</span>
                          {String(a.visibility || 'visible').toLowerCase() === 'hidden' ? (
                            <>
                              <Chip size="small" color="warning" variant="outlined" label="Suspicious ERC-20" sx={{ width: 'fit-content', height: 20 }} />
                              <Tooltip title={String(a.contract_address || 'Contract unavailable')}>
                                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                                  {shortContract(a.contract_address) || 'Contract unavailable'}
                                </Typography>
                              </Tooltip>
                            </>
                          ) : null}
                        </Stack>
                      </Stack>
                    </TableCell>
                    <TableCell>{accountDisplay(a)}</TableCell>
                    <TableCell>{a.chain ? String(a.chain).toUpperCase() : '-'}</TableCell>
                    <TableCell>{Number(a.quantity || 0).toFixed(8)}</TableCell>
                    <TableCell>
                      {Number(a.price_usd || 0) > 0
                        ? formatUnitPrice(
                            Number(a.price_usd || 0),
                            'USD',
                            Number(a.value_eur || 0),
                            Number(a.value_usd || 0)
                          )
                        : Number(a.price_eur || 0) > 0
                          ? formatUnitPrice(
                              Number(a.price_eur || 0),
                              'EUR',
                              Number(a.value_eur || 0),
                              Number(a.value_usd || 0)
                            )
                          : '-'}
                    </TableCell>
                    <TableCell>{formatEur(Number(a.value_eur || 0))}</TableCell>
                    <TableCell>{formatUsd(Number(a.value_usd || 0))}</TableCell>
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
