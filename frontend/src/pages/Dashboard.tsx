import React from 'react'
import SyncRoundedIcon from '@mui/icons-material/SyncRounded'
import { Alert, Box, Button, Card, CardContent, Chip, CircularProgress, Grid, Stack, Typography } from '@mui/material'
import { fetchAssetIcons, fetchAssets, fetchLatestSnapshot, fetchNfts, fetchSyncStatus, syncNow, type SyncStatus } from '../shared/api'
import { formatEur, formatUsd } from '../shared/format'

type Notice = { type: 'success' | 'error'; text: string } | null

function hexToRgba(hex: string, alpha: number): string {
  const clean = hex.replace('#', '')
  if (clean.length !== 6) return `rgba(91, 141, 239, ${alpha})`
  const n = Number.parseInt(clean, 16)
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'unknown'
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return 'unknown'
  const date = dt.toLocaleDateString('en-GB')
  const time = dt.toLocaleTimeString('en-GB')
  return `${date} ${time}`
}

function parseDateMs(value: string | null | undefined): number | null {
  if (!value) return null
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return null
  return dt.getTime()
}

function formatDuration(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(safe / 60)
  const seconds = safe % 60
  if (minutes <= 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

const ICON_SYMBOL_ALIASES: Record<string, string[]> = {
  GUN: ['gunz', 'gun'],
  GPS: ['goplus-security', 'goplus', 'gps'],
}

function AssetIcon({ symbol, iconUrl, size = 22 }: { symbol: string; iconUrl?: string; size?: number }) {
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
  }, [normalized])

  if (!src || symbol === 'Other') {
    return (
      <span
        className="asset-icon-fallback"
        style={{ width: size, height: size, fontSize: Math.max(10, Math.floor(size * 0.45)) }}
        aria-hidden="true"
      >
        {symbol.slice(0, 1)}
      </span>
    )
  }

  return (
      <img
        className="asset-icon"
        src={src}
        alt={`${symbol} icon`}
        width={size}
        height={size}
        onError={() => {
          if (sourceIndex < sources.length - 1) {
            setSourceIndex((idx) => idx + 1)
          } else {
            setSourceIndex(sources.length)
          }
        }}
        loading="lazy"
      />
    )
  }

export default function Dashboard() {
  const [snapshot, setSnapshot] = React.useState<any>(null)
  const [assets, setAssets] = React.useState<any[]>([])
  const [nfts, setNfts] = React.useState<any[]>([])
  const [assetIcons, setAssetIcons] = React.useState<Record<string, string>>({})
  const totalEur = snapshot?.total_eur ? Number(snapshot.total_eur) : 0
  const totalUsd = snapshot?.total_usd ? Number(snapshot.total_usd) : 0
  const [syncLoading, setSyncLoading] = React.useState(false)
  const [syncStatus, setSyncStatus] = React.useState<SyncStatus | null>(null)
  const [notice, setNotice] = React.useState<Notice>(null)
  const [hoveredSegment, setHoveredSegment] = React.useState<string | null>(null)
  const [tooltipPos, setTooltipPos] = React.useState<{ x: number; y: number } | null>(null)
  const [hoveredClassSegment, setHoveredClassSegment] = React.useState<string | null>(null)
  const [classTooltipPos, setClassTooltipPos] = React.useState<{ x: number; y: number } | null>(null)
  const [chartsBuildProgress, setChartsBuildProgress] = React.useState(0)
  const [animatedTotalEur, setAnimatedTotalEur] = React.useState(0)
  const [animatedTotalUsd, setAnimatedTotalUsd] = React.useState(0)
  const [nowMs, setNowMs] = React.useState<number>(() => Date.now())
  const donutRef = React.useRef<HTMLDivElement | null>(null)
  const classRef = React.useRef<HTMLDivElement | null>(null)
  const prevTotalsRef = React.useRef<{ eur: number; usd: number }>({ eur: 0, usd: 0 })
  const lastSyncedAt = React.useMemo(() => {
    if (syncStatus?.finished_at) return syncStatus.finished_at
    if (snapshot?.timestamp) return snapshot.timestamp
    return null
  }, [snapshot?.timestamp, syncStatus?.finished_at])

  function formatSyncMessage(status: SyncStatus): string {
    if (
      status.status === 'completed'
      && status.holdings_count != null
      && status.nfts_count != null
    ) {
      return `${status.holdings_count} holdings and ${status.nfts_count} NFTs`
    }
    return status.message || 'Sync completed.'
  }

  React.useEffect(() => {
    Promise.all([fetchLatestSnapshot(), fetchAssets(), fetchNfts()])
      .then(([latestSnapshot, latestAssets, latestNfts]) => {
        setSnapshot(latestSnapshot)
        setAssets(latestAssets || [])
        setNfts(latestNfts || [])
      })
      .catch(() => {})
  }, [])

  React.useEffect(() => {
    const symbols = Array.from(new Set(assets.map((a) => String(a.asset_symbol || '').toUpperCase()).filter(Boolean)))
    if (symbols.length === 0) {
      setAssetIcons({})
      return
    }
    fetchAssetIcons(symbols)
      .then((icons) => setAssetIcons(icons || {}))
      .catch(() => setAssetIcons({}))
  }, [assets])

  React.useEffect(() => {
    fetchSyncStatus()
      .then((status) => {
        setSyncStatus(status)
        setSyncLoading(status.status === 'running')
      })
      .catch(() => {})
  }, [])

  React.useEffect(() => {
    if (!syncLoading) return
    const timer = window.setInterval(async () => {
      try {
        const status = await fetchSyncStatus()
        setSyncStatus(status)
        if (status.status === 'running') return

        setSyncLoading(false)
        if (status.status === 'completed') {
          setNotice({ type: 'success', text: formatSyncMessage(status) })
          const [latestSnap, latestAssets, latestNfts] = await Promise.all([fetchLatestSnapshot(), fetchAssets(), fetchNfts()])
          setSnapshot(latestSnap)
          setAssets(latestAssets)
          setNfts(latestNfts)
        } else if (status.status === 'failed') {
          setNotice({ type: 'error', text: status.message || 'Sync failed.' })
        }
      } catch {
        setSyncLoading(false)
      }
    }, 1000)

    return () => window.clearInterval(timer)
  }, [syncLoading])

  React.useEffect(() => {
    if (syncStatus?.status !== 'running') return
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [syncStatus?.status])

  React.useEffect(() => {
    const fromEur = prevTotalsRef.current.eur
    const fromUsd = prevTotalsRef.current.usd
    const toEur = totalEur
    const toUsd = totalUsd
    if (fromEur === toEur && fromUsd === toUsd) return

    const durationMs = 620
    const start = performance.now()
    let raf = 0

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs)
      const eased = 1 - Math.pow(1 - t, 3)
      setAnimatedTotalEur(fromEur + (toEur - fromEur) * eased)
      setAnimatedTotalUsd(fromUsd + (toUsd - fromUsd) * eased)
      if (t < 1) {
        raf = window.requestAnimationFrame(tick)
      } else {
        prevTotalsRef.current = { eur: toEur, usd: toUsd }
      }
    }

    raf = window.requestAnimationFrame(tick)
    return () => window.cancelAnimationFrame(raf)
  }, [totalEur, totalUsd])

  async function triggerSync() {
    setNotice(null)
    try {
      const res = await syncNow()
      if (res?.status === 'already_running') {
        setNotice({ type: 'success', text: 'A sync is already running.' })
      } else {
        setNotice({ type: 'success', text: 'Sync started' })
      }
      setSyncLoading(true)
      const status = await fetchSyncStatus()
      if (status?.status === 'running') {
        setSyncStatus({ ...status, finished_at: null })
      } else {
        setSyncStatus(status)
      }
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to start sync: ${error?.message || 'unknown error'}` })
    }
  }

  const allocationRows = React.useMemo(() => {
    const bySymbol = new Map<string, { symbol: string; valueEur: number; valueUsd: number }>()
    for (const a of assets) {
      const symbol = String(a.asset_symbol || '')
      if (!symbol) continue
      const curr = bySymbol.get(symbol) || { symbol, valueEur: 0, valueUsd: 0 }
      curr.valueEur += Number(a.value_eur || 0)
      curr.valueUsd += Number(a.value_usd || 0)
      bySymbol.set(symbol, curr)
    }
    const rows = Array.from(bySymbol.values()).filter((r) => r.valueEur > 0).sort((a, b) => b.valueEur - a.valueEur)
    if (rows.length === 0) return []
    const total = rows.reduce((acc, row) => acc + row.valueEur, 0)
    return rows.map((row) => ({ ...row, pct: total > 0 ? (row.valueEur / total) * 100 : 0 }))
  }, [assets])

  const topCount = 6
  const topRows = allocationRows.slice(0, topCount)
  const otherRows = allocationRows.slice(topCount)
  const otherPct = otherRows.reduce((acc, row) => acc + row.pct, 0)
  const otherValueEur = otherRows.reduce((acc, row) => acc + row.valueEur, 0)
  const otherValueUsd = otherRows.reduce((acc, row) => acc + row.valueUsd, 0)

  const palette = ['#5b8def', '#ff9800', '#ffb74d', '#8b80f9', '#ff5e5e', '#d9a15b', '#f57c00']
  const donutSegments = topRows.map((row, idx) => ({
    name: row.symbol,
    pct: row.pct,
    valueEur: row.valueEur,
    valueUsd: row.valueUsd,
    color: palette[idx % palette.length],
  }))
  if (otherPct > 0) {
    donutSegments.push({ name: 'Other', pct: otherPct, valueEur: otherValueEur, valueUsd: otherValueUsd, color: '#f57c00' })
  }
  const legendRightSegments = React.useMemo(() => {
    const other = donutSegments.find((segment) => segment.name === 'Other')
    if (other) return [other]
    if (donutSegments.length <= 1) return donutSegments
    return [donutSegments[donutSegments.length - 1]]
  }, [donutSegments])
  const legendRightNames = React.useMemo(() => new Set(legendRightSegments.map((segment) => segment.name)), [legendRightSegments])
  const legendLeftSegments = React.useMemo(
    () => donutSegments.filter((segment) => !legendRightNames.has(segment.name)),
    [donutSegments, legendRightNames]
  )

  const donutSvgSegments = React.useMemo(() => {
    let startPct = 0
    return donutSegments.map((segment) => {
      const out = { ...segment, startPct }
      startPct += segment.pct
      return out
    })
  }, [donutSegments])
  const donutRenderSegments = React.useMemo(() => {
    if (!hoveredSegment) return donutSvgSegments
    const inactive = donutSvgSegments.filter((segment) => segment.name !== hoveredSegment)
    const active = donutSvgSegments.find((segment) => segment.name === hoveredSegment)
    return active ? [...inactive, active] : donutSvgSegments
  }, [donutSvgSegments, hoveredSegment])

  const primary = donutSegments[0]
  const activeSegment = donutSegments.find((segment) => segment.name === hoveredSegment) || primary
  const donutRadius = 78
  const donutCircumference = 2 * Math.PI * donutRadius

  function updateTooltipPosition(event: React.MouseEvent<SVGCircleElement | HTMLDivElement>) {
    const host = donutRef.current?.getBoundingClientRect()
    if (!host) return
    setTooltipPos({ x: event.clientX - host.left + 12, y: event.clientY - host.top - 12 })
  }

  function handleLegendMouseMove(event: React.MouseEvent<HTMLDivElement>) {
    const host = event.currentTarget
    const directItem = (event.target as HTMLElement).closest('.allocation-item') as HTMLElement | null
    if (directItem?.dataset.name) {
      const name = directItem.dataset.name
      if (name && name !== hoveredSegment) setHoveredSegment(name)
      return
    }

    const items = Array.from(host.querySelectorAll<HTMLElement>('.allocation-item[data-name]'))
    if (items.length === 0) return

    const x = event.clientX
    const y = event.clientY
    let closestName: string | null = null
    let closestDistance = Number.POSITIVE_INFINITY

    for (const item of items) {
      const rect = item.getBoundingClientRect()
      const centerX = rect.left + rect.width / 2
      const centerY = rect.top + rect.height / 2
      const dx = x - centerX
      const dy = y - centerY
      const distance = Math.hypot(dx, dy)
      if (distance < closestDistance) {
        closestDistance = distance
        closestName = item.dataset.name || null
      }
    }

    if (closestName && closestName !== hoveredSegment) {
      setHoveredSegment(closestName)
    }
  }

  const classData = React.useMemo(() => {
    const stableSymbols = new Set(['USDC', 'USDT'])
    let stableEur = 0
    let stableUsd = 0
    let otherCoinsEur = 0
    let otherCoinsUsd = 0
    let nftsEur = 0
    let nftsUsd = 0
    for (const a of assets) {
      const sym = String(a.asset_symbol || '').toUpperCase()
      const valEur = Number(a.value_eur || 0)
      const valUsd = Number(a.value_usd || 0)
      const safeEur = Number.isFinite(valEur) ? valEur : 0
      const safeUsd = Number.isFinite(valUsd) ? valUsd : 0
      if (safeEur <= 0 && safeUsd <= 0) continue
      if (stableSymbols.has(sym)) {
        stableEur += safeEur
        stableUsd += safeUsd
      } else {
        otherCoinsEur += safeEur
        otherCoinsUsd += safeUsd
      }
    }
    for (const n of nfts) {
      const valEur = Number(n.valuation_eur || 0)
      const valUsd = Number(n.valuation_usd || 0)
      if (Number.isFinite(valEur) && valEur > 0) nftsEur += valEur
      if (Number.isFinite(valUsd) && valUsd > 0) nftsUsd += valUsd
    }
    const coinsEur = stableEur + otherCoinsEur
    const coinsUsd = stableUsd + otherCoinsUsd
    const totalEur = coinsEur + nftsEur

    const primary = [
      { key: 'coins', label: 'Coins', valueEur: coinsEur, valueUsd: coinsUsd, color: '#2563eb' },
      { key: 'nfts', label: 'NFTs', valueEur: nftsEur, valueUsd: nftsUsd, color: '#0f766e' },
    ]
      .filter((r) => r.valueEur > 0)
      .map((r) => ({ ...r, pctTotal: totalEur > 0 ? (r.valueEur / totalEur) * 100 : 0 }))

    const childCoins = [
      { key: 'stable', label: 'Stable Coins', valueEur: stableEur, valueUsd: stableUsd, color: '#bfdbfe' },
      { key: 'other_coins', label: 'Other Coins', valueEur: otherCoinsEur, valueUsd: otherCoinsUsd, color: '#93c5fd' },
    ]
      .filter((r) => r.valueEur > 0)
      .map((r) => ({
        ...r,
        pctTotal: totalEur > 0 ? (r.valueEur / totalEur) * 100 : 0,
        pctCoins: coinsEur > 0 ? (r.valueEur / coinsEur) * 100 : 0,
      }))

    return { primary, childCoins, totalEur }
  }, [assets, nfts])

  const activeClassSegment = React.useMemo(() => {
    const all = [...classData.primary, ...classData.childCoins]
    return all.find((s) => s.key === hoveredClassSegment) || null
  }, [classData.childCoins, classData.primary, hoveredClassSegment])
  const classCoinsSegment = React.useMemo(
    () => classData.primary.find((s) => s.key === 'coins') || null,
    [classData.primary]
  )
  const classPrimaryWithStart = React.useMemo(() => {
    let startPct = 0
    return classData.primary.map((segment) => {
      const out = { ...segment, startPct }
      startPct += segment.pctTotal
      return out
    })
  }, [classData.primary])
  const classChildWithStart = React.useMemo(() => {
    let startPct = 0
    return classData.childCoins.map((segment) => {
      const out = { ...segment, startPct }
      startPct += segment.pctCoins
      return out
    })
  }, [classData.childCoins])
  const chartAnimationSignature = React.useMemo(() => {
    const donutSig = donutSegments.map((s) => `${s.name}:${s.pct.toFixed(4)}`).join('|')
    const primarySig = classData.primary.map((s) => `${s.key}:${s.pctTotal.toFixed(4)}`).join('|')
    const childSig = classData.childCoins.map((s) => `${s.key}:${s.pctCoins.toFixed(4)}`).join('|')
    return `${donutSig}__${primarySig}__${childSig}`
  }, [classData.childCoins, classData.primary, donutSegments])

  React.useEffect(() => {
    if (donutSegments.length === 0 && classData.primary.length === 0) return
    setChartsBuildProgress(0)
    let raf1 = 0
    let raf2 = 0
    raf1 = window.requestAnimationFrame(() => {
      raf2 = window.requestAnimationFrame(() => setChartsBuildProgress(1))
    })
    return () => {
      window.cancelAnimationFrame(raf1)
      window.cancelAnimationFrame(raf2)
    }
  }, [chartAnimationSignature, classData.primary.length, donutSegments.length])

  function updateClassTooltip(event: React.MouseEvent<HTMLDivElement>, key: string) {
    const host = classRef.current?.getBoundingClientRect()
    if (!host) return
    setHoveredClassSegment(key)
    setClassTooltipPos({ x: event.clientX - host.left + 12, y: event.clientY - host.top - 10 })
  }

  const startedMs = parseDateMs(syncStatus?.started_at)
  const finishedMs = parseDateMs(syncStatus?.finished_at)
  const runningElapsedSeconds = React.useMemo(() => {
    if (syncStatus?.status !== 'running' || startedMs == null) return null
    return Math.max(0, Math.floor((nowMs - startedMs) / 1000))
  }, [nowMs, startedMs, syncStatus?.status])
  const completedDurationSeconds = React.useMemo(() => {
    if (syncStatus?.status !== 'completed' || startedMs == null || finishedMs == null) return null
    return Math.max(0, Math.floor((finishedMs - startedMs) / 1000))
  }, [finishedMs, startedMs, syncStatus?.status])

  return (
    <Stack spacing={2}>
      {notice ? (
        <Alert
          severity={notice.type}
          sx={
            notice.type === 'success'
              ? {
                  border: 1,
                  borderColor: 'success.dark',
                }
              : undefined
          }
        >
          {notice.text}
        </Alert>
      ) : null}

      <Card variant="outlined">
        <CardContent>
          <Grid container spacing={3} alignItems="flex-start">
            <Grid item xs={12} md={7}>
              <Stack spacing={2}>
                <Typography variant="h5">Total Portfolio</Typography>

                <Grid container spacing={2}>
                  <Grid item xs={12} sm={6}>
                    <Box sx={{ p: 0.5 }}>
                      <Typography variant="overline" color="text.secondary">EUR</Typography>
                      <Typography variant="h3" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
                        {formatEur(animatedTotalEur, { withCode: false })}
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <Box sx={{ p: 0.5 }}>
                      <Typography variant="overline" color="text.secondary">USD</Typography>
                      <Typography variant="h3" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
                        {formatUsd(animatedTotalUsd, { withCode: false })}
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
              </Stack>
            </Grid>
            <Grid item xs={12} md={5}>
              <Stack
                alignItems="flex-end"
                sx={{
                  textAlign: 'right',
                  height: '100%',
                  minHeight: { xs: 'auto', md: 184 },
                  justifyContent: { xs: 'flex-start', md: 'space-between' },
                }}
              >
                <Stack spacing={1.5} alignItems="flex-end">
                  <Typography variant="body2" color="text.secondary">
                    Last update: {snapshot?.timestamp ? formatDateTime(snapshot.timestamp) : 'n/a'}
                  </Typography>
                  {syncStatus?.warning ? <Alert severity="warning">{syncStatus.warning}</Alert> : null}
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Button
                      variant="contained"
                      onClick={triggerSync}
                      disabled={syncLoading}
                      startIcon={syncLoading ? <CircularProgress size={16} color="inherit" /> : <SyncRoundedIcon />}
                      sx={{
                        minWidth: 120,
                        ...(syncLoading
                          ? {
                              boxShadow: (theme) => `0 0 0 4px ${theme.palette.primary.main}22`,
                            }
                          : null),
                      }}
                    >
                      {syncLoading ? 'Syncing...' : 'Sync'}
                    </Button>
                  </Stack>
                </Stack>
                {syncStatus ? (
                  <Stack spacing={0.5} alignItems="flex-end">
                    {syncStatus.status !== 'idle' ? (
                      <>
                        {syncStatus.status === 'running' || syncStatus.status === 'failed' ? (
                          <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end" sx={{ width: '100%' }}>
                            <Chip
                              size="small"
                              label={syncStatus.status.toUpperCase()}
                              color={syncStatus.status === 'failed' ? 'error' : 'primary'}
                            />
                            {syncStatus.status === 'running' ? (
                              <Typography variant="body2" color="text.secondary">
                                Progress: <strong>{syncStatus.progress}%</strong>
                              </Typography>
                            ) : null}
                          </Stack>
                        ) : null}
                        {syncStatus.status === 'completed' ? (
                          <Typography variant="body2" color="text.secondary">
                            {formatSyncMessage(syncStatus)}
                          </Typography>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            {formatSyncMessage(syncStatus)}
                          </Typography>
                        )}
                        {syncStatus.status === 'running' && syncStatus.started_at ? (
                          <Typography variant="body2" color="text.secondary">Started: {formatDateTime(syncStatus.started_at)}</Typography>
                        ) : null}
                        {syncStatus.status === 'running' && runningElapsedSeconds != null ? (
                          <Typography variant="body2" color="text.secondary">
                            Elapsed: {formatDuration(runningElapsedSeconds)}
                          </Typography>
                        ) : null}
                        {syncStatus.status === 'completed' && completedDurationSeconds != null ? (
                          <Typography variant="body2" color="text.secondary">Duration: {formatDuration(completedDurationSeconds)}</Typography>
                        ) : null}
                      </>
                    ) : null}
                    {syncStatus.status === 'idle' && snapshot ? (
                      <>
                        <Typography variant="body2" color="text.secondary">
                          Last successful sync: <strong>{formatDateTime(lastSyncedAt)}</strong>
                        </Typography>
                      </>
                    ) : null}
                  </Stack>
                ) : null}
              </Stack>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Coin Allocation</Typography>
          {donutSegments.length === 0 ? (
            <Typography color="text.secondary">No coin data available to calculate allocation.</Typography>
          ) : (
            <div className="allocation-layout">
              <div className="donut-wrap">
                <div
                  className="donut"
                  ref={donutRef}
                  onMouseLeave={() => {
                    setHoveredSegment(null)
                    setTooltipPos(null)
                  }}
                >
                  <svg className="donut-svg" viewBox="0 0 200 200" aria-label="Coin allocation donut chart">
                    <g transform="rotate(-90 100 100)">
                      <circle cx="100" cy="100" r={donutRadius} stroke="rgba(128, 128, 128, 0.35)" strokeWidth="30" fill="none" />
                      {donutRenderSegments.map((segment) => {
                        const isHovered = hoveredSegment === segment.name
                        const hasHovered = Boolean(hoveredSegment)
                        return (
                        <circle
                          key={segment.name}
                          cx="100"
                          cy="100"
                          r={donutRadius}
                          fill="none"
                          stroke={segment.color}
                          strokeWidth={isHovered ? 38 : 30}
                          opacity={hasHovered && !isHovered ? 0.3 : 1}
                          strokeDasharray={`${((segment.pct * chartsBuildProgress) / 100) * donutCircumference} ${donutCircumference}`}
                          strokeDashoffset={-(segment.startPct / 100) * donutCircumference}
                          style={{ transition: 'stroke-dasharray 560ms ease-out, stroke-width 140ms ease, opacity 140ms ease' }}
                          onMouseEnter={() => setHoveredSegment(segment.name)}
                          onMouseMove={updateTooltipPosition}
                          onMouseLeave={() => {
                            setHoveredSegment(null)
                            setTooltipPos(null)
                          }}
                        />
                        )
                      })}
                    </g>
                  </svg>

                  <Box
                    className="donut-hole"
                    sx={{
                      bgcolor: 'background.paper',
                      borderColor: 'divider',
                      opacity: chartsBuildProgress,
                      transform: chartsBuildProgress < 1 ? 'translate(-50%, -50%) scale(0.97)' : 'translate(-50%, -50%) scale(1)',
                      transition: 'opacity 420ms ease-out, transform 420ms ease-out',
                    }}
                  >
                    <Typography variant="h6" className="donut-title" sx={{ fontWeight: 400 }}>
                      <AssetIcon
                        symbol={String(activeSegment?.name || '')}
                        iconUrl={assetIcons[String(activeSegment?.name || '').toUpperCase()]}
                        size={24}
                      />
                      <span>{activeSegment?.name}</span>
                    </Typography>
                    <Typography className="donut-value" sx={{ fontWeight: 800 }}>
                      €{formatEur(Number(activeSegment?.valueEur || 0), { withCode: false })}
                    </Typography>
                    <Typography className="donut-subvalue" sx={{ fontWeight: 800 }}>
                      ${formatUsd(Number(activeSegment?.valueUsd || 0), { withCode: false })}
                    </Typography>
                    <Typography color="text.secondary">{Number(activeSegment?.pct || 0).toFixed(2)}%</Typography>
                  </Box>

                  {hoveredSegment && activeSegment && tooltipPos ? (
                    <Box className="donut-tooltip" sx={{ left: tooltipPos.x, top: tooltipPos.y, bgcolor: 'background.paper', borderColor: 'divider' }}>
                      {activeSegment.name}: {activeSegment.pct.toFixed(2)}%
                    </Box>
                  ) : null}
                </div>
              </div>

              <div
                className="allocation-legend-grid"
                onMouseMove={handleLegendMouseMove}
                onMouseLeave={() => setHoveredSegment(null)}
              >
                <div className="allocation-legend-column">
                  {legendLeftSegments.map((segment) => (
                    <div
                      key={segment.name}
                      className={`allocation-item ${activeSegment?.name === segment.name ? 'allocation-item-active' : ''}`}
                      data-name={segment.name}
                      onMouseEnter={() => setHoveredSegment(segment.name)}
                      style={
                        activeSegment?.name === segment.name
                          ? {
                              borderColor: hexToRgba(segment.color, 0.65),
                              boxShadow: `inset 0 0 0 1px ${hexToRgba(segment.color, 0.5)}`,
                              background: hexToRgba(segment.color, 0.12),
                            }
                          : undefined
                      }
                    >
                      <span className="alloc-name">
                        <AssetIcon symbol={segment.name} iconUrl={assetIcons[segment.name.toUpperCase()]} />
                        <span>{segment.name}</span>
                      </span>
                      <span className="alloc-pct">{segment.pct < 0.1 ? '< 0.1%' : `${segment.pct.toFixed(2)}%`}</span>
                      <span className="alloc-dot" style={{ background: segment.color }} />
                    </div>
                  ))}
                </div>
                <div className="allocation-legend-column allocation-legend-column-right">
                  {legendRightSegments.map((segment) => (
                    <div
                      key={segment.name}
                      className={`allocation-item ${activeSegment?.name === segment.name ? 'allocation-item-active' : ''}`}
                      data-name={segment.name}
                      onMouseEnter={() => setHoveredSegment(segment.name)}
                      style={
                        activeSegment?.name === segment.name
                          ? {
                              borderColor: hexToRgba(segment.color, 0.65),
                              boxShadow: `inset 0 0 0 1px ${hexToRgba(segment.color, 0.5)}`,
                              background: hexToRgba(segment.color, 0.12),
                            }
                          : undefined
                      }
                    >
                      <span className="alloc-name">
                        <AssetIcon symbol={segment.name} iconUrl={assetIcons[segment.name.toUpperCase()]} />
                        <span>{segment.name}</span>
                      </span>
                      <span className="alloc-pct">{segment.pct < 0.1 ? '< 0.1%' : `${segment.pct.toFixed(2)}%`}</span>
                      <span className="alloc-dot" style={{ background: segment.color }} />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Portfolio Classification</Typography>
          {classData.primary.length === 0 ? (
            <Typography color="text.secondary">No data available to calculate classification.</Typography>
          ) : (
            <Stack spacing={2.25}>
              <Box
                ref={classRef}
                sx={{ position: 'relative' }}
                onMouseLeave={() => {
                  setHoveredClassSegment(null)
                  setClassTooltipPos(null)
                }}
              >
                <Stack spacing={1.75}>
                  <Box sx={{ position: 'relative', height: 18, width: '100%' }}>
                    {classPrimaryWithStart.map((segment) => (
                          <Typography
                            key={`class-main-label-${segment.key}`}
                            variant="caption"
                            sx={{
                              position: 'absolute',
                              left: `${segment.startPct}%`,
                              top: 0,
                              color: 'text.secondary',
                              fontWeight: 600,
                              whiteSpace: 'nowrap',
                              opacity: chartsBuildProgress,
                              transition: 'opacity 340ms ease-out',
                              pointerEvents: 'none',
                            }}
                          >
                        {segment.label}
                      </Typography>
                    ))}
                  </Box>
                  <Box
                    sx={{
                      height: 30,
                      borderRadius: 999,
                      overflow: 'hidden',
                      border: (theme) => `1px solid ${theme.palette.divider}`,
                      bgcolor: 'action.hover',
                      display: 'flex',
                    }}
                  >
                    {classData.primary.map((segment, idx) => {
                      const isActive = hoveredClassSegment === segment.key
                      const hasHover = Boolean(hoveredClassSegment)
                      return (
                        <Box
                          key={segment.key}
                          onMouseEnter={(e) => updateClassTooltip(e, segment.key)}
                          onMouseMove={(e) => updateClassTooltip(e, segment.key)}
                          sx={{
                            width: `${segment.pctTotal * chartsBuildProgress}%`,
                            minWidth: chartsBuildProgress < 1 ? 0 : segment.pctTotal > 0 ? 6 : 0,
                            height: '100%',
                            backgroundColor: segment.color,
                            cursor: 'pointer',
                            position: 'relative',
                            transition: 'width 560ms ease-out, filter 140ms ease, opacity 140ms ease, box-shadow 140ms ease',
                            opacity: hasHover && !isActive ? 0.65 : 1,
                            filter: isActive ? 'saturate(1.2) brightness(1.05)' : 'none',
                            boxShadow: isActive ? `inset 0 0 0 2px ${hexToRgba('#ffffff', 0.85)}` : 'none',
                            ...(idx === 0 ? { borderTopLeftRadius: 999, borderBottomLeftRadius: 999 } : {}),
                            ...(idx === classData.primary.length - 1
                              ? { borderTopRightRadius: 999, borderBottomRightRadius: 999 }
                              : { borderRight: '2px solid', borderColor: 'background.paper' }),
                          }}
                        />
                      )
                    })}
                  </Box>
                  {classData.childCoins.length > 0 ? (
                    <Stack spacing={0.7}>
                      <Box sx={{ position: 'relative', height: 16, width: `${classCoinsSegment?.pctTotal || 0}%`, minWidth: classCoinsSegment ? 40 : 0 }}>
                        {classChildWithStart.map((segment) => (
                          <Typography
                            key={`class-child-label-${segment.key}`}
                            variant="caption"
                            sx={{
                              position: 'absolute',
                              left: `${segment.startPct}%`,
                              top: 0,
                              color: 'text.secondary',
                              fontWeight: 600,
                              whiteSpace: 'nowrap',
                              opacity: chartsBuildProgress,
                              transition: 'opacity 340ms ease-out',
                              pointerEvents: 'none',
                            }}
                          >
                            {segment.key === 'other_coins' ? 'Others' : segment.label}
                          </Typography>
                        ))}
                      </Box>
                      <Box
                        sx={{
                          ml: 0,
                          width: `${(classCoinsSegment?.pctTotal || 0) * chartsBuildProgress}%`,
                          minWidth: classCoinsSegment ? 40 : 0,
                          height: 20,
                          borderRadius: 999,
                          overflow: 'hidden',
                          border: (theme) => `1px solid ${theme.palette.divider}`,
                          bgcolor: 'action.hover',
                          display: 'flex',
                          transition: 'width 560ms ease-out',
                        }}
                      >
                        {classData.childCoins.map((segment, idx) => {
                          const isActive = hoveredClassSegment === segment.key
                          const hasHover = Boolean(hoveredClassSegment)
                          return (
                            <Box
                              key={segment.key}
                              onMouseEnter={(e) => updateClassTooltip(e, segment.key)}
                              onMouseMove={(e) => updateClassTooltip(e, segment.key)}
                              sx={{
                                width: `${segment.pctCoins * chartsBuildProgress}%`,
                                minWidth: chartsBuildProgress < 1 ? 0 : segment.pctCoins > 0 ? 4 : 0,
                                height: '100%',
                                backgroundColor: segment.color,
                                cursor: 'pointer',
                                transition: 'width 560ms ease-out, filter 140ms ease, opacity 140ms ease, box-shadow 140ms ease',
                                opacity: hasHover && !isActive ? 0.7 : 1,
                                filter: isActive ? 'saturate(1.2) brightness(1.05)' : 'none',
                                boxShadow: isActive ? `inset 0 0 0 2px ${hexToRgba('#ffffff', 0.85)}` : 'none',
                                ...(idx < classData.childCoins.length - 1
                                  ? { borderRight: '2px solid', borderColor: 'background.paper' }
                                  : {}),
                              }}
                            />
                          )
                        })}
                      </Box>
                    </Stack>
                  ) : null}
                </Stack>
                {activeClassSegment && classTooltipPos ? (
                  <Box
                    sx={{
                      position: 'absolute',
                      left: classTooltipPos.x,
                      top: classTooltipPos.y,
                      transform: 'translate(-50%, -100%)',
                      px: 1,
                      py: 0.5,
                      borderRadius: 1,
                      bgcolor: 'background.paper',
                      border: (theme) => `1px solid ${theme.palette.divider}`,
                      boxShadow: 4,
                      zIndex: 1000,
                      fontSize: 12,
                      fontWeight: 600,
                      pointerEvents: 'none',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {activeClassSegment.label}: {formatEur(activeClassSegment.valueEur)} | {formatUsd(activeClassSegment.valueUsd)} (
                    {activeClassSegment.key === 'stable' || activeClassSegment.key === 'other_coins'
                      ? `${activeClassSegment.pctTotal.toFixed(2)}% total, ${activeClassSegment.pctCoins.toFixed(2)}% of Coins`
                      : `${activeClassSegment.pctTotal.toFixed(2)}% total`}
                    )
                  </Box>
                ) : null}
              </Box>

              <Stack spacing={1}>
                {classData.primary
                  .filter((segment) => segment.key === 'coins')
                  .map((segment) => (
                    <Box key={segment.key}>
                      <Stack
                        direction="row"
                        spacing={1.2}
                        alignItems="center"
                        justifyContent="space-between"
                        onMouseEnter={() => setHoveredClassSegment(segment.key)}
                        onMouseLeave={() => setHoveredClassSegment(null)}
                        sx={{
                          cursor: 'default',
                          px: 1,
                          py: 0.75,
                          borderRadius: 1.5,
                          background: hoveredClassSegment === segment.key ? hexToRgba(segment.color, 0.08) : 'transparent',
                        }}
                      >
                        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                          <Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: segment.color, flexShrink: 0 }} />
                          <Typography variant="body2" sx={{ fontWeight: 500 }}>
                            {segment.label}
                          </Typography>
                          <Typography variant="body2" sx={{ color: 'text.primary', whiteSpace: 'nowrap' }}>
                            <strong>{formatEur(segment.valueEur)}</strong> | <strong>{formatUsd(segment.valueUsd)}</strong>
                          </Typography>
                        </Stack>
                        <Chip
                          size="small"
                          variant="outlined"
                          label={`${segment.pctTotal.toFixed(2)}%`}
                          sx={{
                            fontWeight: 600,
                            borderColor: hexToRgba(segment.color, 0.45),
                            backgroundColor: hexToRgba(segment.color, 0.12),
                            color: 'text.primary',
                          }}
                        />
                      </Stack>

                      <Stack spacing={0.5} sx={{ ml: 1.4, pl: 2, borderLeft: (theme) => `1px dashed ${theme.palette.divider}` }}>
                        {classData.childCoins.map((child) => (
                          <Stack
                            key={child.key}
                            direction="row"
                            spacing={1.2}
                            alignItems="center"
                            justifyContent="space-between"
                            onMouseEnter={() => setHoveredClassSegment(child.key)}
                            onMouseLeave={() => setHoveredClassSegment(null)}
                            sx={{
                              cursor: 'default',
                              px: 1,
                              py: 0.6,
                              borderRadius: 1.25,
                              background: hoveredClassSegment === child.key ? hexToRgba(child.color, 0.1) : 'transparent',
                            }}
                          >
                            <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                              <Box sx={{ width: 9, height: 9, borderRadius: 0.5, bgcolor: child.color, flexShrink: 0 }} />
                              <Typography variant="body2" color="text.secondary">
                                {child.label}
                              </Typography>
                              <Typography variant="body2" sx={{ color: 'text.primary', whiteSpace: 'nowrap' }}>
                                <strong>{formatEur(child.valueEur)}</strong> | <strong>{formatUsd(child.valueUsd)}</strong>
                              </Typography>
                            </Stack>
                            <Chip
                              size="small"
                              variant="outlined"
                              label={`${child.pctCoins.toFixed(2)}% of Coins`}
                              sx={{
                                fontWeight: 500,
                                borderColor: hexToRgba(child.color, 0.45),
                                backgroundColor: hexToRgba(child.color, 0.12),
                                color: 'text.primary',
                              }}
                            />
                          </Stack>
                        ))}
                      </Stack>
                    </Box>
                  ))}

                {classData.primary
                  .filter((segment) => segment.key !== 'coins')
                  .map((segment) => (
                    <Stack
                      key={segment.key}
                      direction="row"
                      spacing={1.2}
                      alignItems="center"
                      justifyContent="space-between"
                      onMouseEnter={() => setHoveredClassSegment(segment.key)}
                      onMouseLeave={() => setHoveredClassSegment(null)}
                      sx={{
                        cursor: 'default',
                        px: 1,
                        py: 0.75,
                        mt: 0.5,
                        borderRadius: 1.5,
                        background: hoveredClassSegment === segment.key ? hexToRgba(segment.color, 0.08) : 'transparent',
                      }}
                    >
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                        <Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: segment.color, flexShrink: 0 }} />
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                          {segment.label}
                        </Typography>
                        <Typography variant="body2" sx={{ color: 'text.primary', whiteSpace: 'nowrap' }}>
                          <strong>{formatEur(segment.valueEur)}</strong> | <strong>{formatUsd(segment.valueUsd)}</strong>
                        </Typography>
                      </Stack>
                      <Chip
                        size="small"
                        variant="outlined"
                        label={`${segment.pctTotal.toFixed(2)}%`}
                        sx={{
                          fontWeight: 600,
                          borderColor: hexToRgba(segment.color, 0.45),
                          backgroundColor: hexToRgba(segment.color, 0.12),
                          color: 'text.primary',
                        }}
                      />
                    </Stack>
                  ))}
              </Stack>
            </Stack>
          )}
        </CardContent>
      </Card>
    </Stack>
  )
}
