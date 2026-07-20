import React from 'react'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import EditRoundedIcon from '@mui/icons-material/EditRounded'
import SaveRoundedIcon from '@mui/icons-material/SaveRounded'
import { Alert, Box, Button, ButtonGroup, Card, CardContent, Checkbox, Chip, Grid, IconButton, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip, Typography } from '@mui/material'
import {
  auditSnapshotHistory,
  createPriceSymbolMapping,
  deletePriceSymbolMapping,
  listSnapshotHistory,
  listPriceSymbolMappings,
  type PriceSymbolMapping,
  type SnapshotAdminRow,
  type SnapshotAuditResult,
  updateSnapshotValidity,
  updatePriceSymbolMapping,
} from '../shared/api'
import { formatEur, formatUsd } from '../shared/format'

type Notice = { type: 'success' | 'error'; text: string } | null
type SnapshotFilter = 'all' | 'valid' | 'invalid'
type MappingForm = {
  symbol: string
  provider_id: string
  label: string
  enabled: boolean
  notes: string
}

const EMPTY_FORM: MappingForm = {
  symbol: '',
  provider_id: '',
  label: '',
  enabled: true,
  notes: '',
}

function toForm(row: PriceSymbolMapping): MappingForm {
  return {
    symbol: row.symbol || '',
    provider_id: row.provider_id || '',
    label: row.label || '',
    enabled: row.enabled,
    notes: row.notes || '',
  }
}

function toPayload(form: MappingForm) {
  return {
    symbol: form.symbol.trim().toUpperCase(),
    provider_id: form.provider_id.trim(),
    label: form.label.trim() || null,
    enabled: form.enabled,
    notes: form.notes.trim() || null,
  }
}

function formatSnapshotTotal(value: number, currency: 'EUR' | 'USD'): string {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return `${currency} invalid`
  if (Math.abs(amount) >= 1_000_000_000_000) {
    return `${currency} ${amount.toExponential(4)}`
  }
  return currency === 'EUR' ? formatEur(amount) : formatUsd(amount)
}

function snapshotTotalDetails(value: number, currency: 'EUR' | 'USD'): string {
  const amount = Number(value || 0)
  if (!Number.isFinite(amount)) return `${currency} invalid numeric value`
  if (Math.abs(amount) >= 1_000_000_000_000) {
    return `${currency} ${amount.toExponential(12)}`
  }
  return currency === 'EUR' ? formatEur(amount) : formatUsd(amount)
}

export default function Settings() {
  const [mappings, setMappings] = React.useState<PriceSymbolMapping[]>([])
  const [loading, setLoading] = React.useState(false)
  const [notice, setNotice] = React.useState<Notice>(null)
  const [newMapping, setNewMapping] = React.useState<MappingForm>(EMPTY_FORM)
  const [editingSymbol, setEditingSymbol] = React.useState<string | null>(null)
  const [editingMapping, setEditingMapping] = React.useState<MappingForm>(EMPTY_FORM)
  const [snapshots, setSnapshots] = React.useState<SnapshotAdminRow[]>([])
  const [snapshotFilter, setSnapshotFilter] = React.useState<SnapshotFilter>('all')
  const [snapshotLoading, setSnapshotLoading] = React.useState(false)
  const [snapshotAudit, setSnapshotAudit] = React.useState<SnapshotAuditResult | null>(null)

  React.useEffect(() => {
    fetchMappings()
  }, [])

  React.useEffect(() => {
    fetchSnapshots(snapshotFilter)
  }, [snapshotFilter])

  async function fetchMappings() {
    setLoading(true)
    try {
      setMappings(await listPriceSymbolMappings())
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to load price mappings: ${error?.message || 'unknown error'}` })
    } finally {
      setLoading(false)
    }
  }

  async function fetchSnapshots(status: SnapshotFilter = snapshotFilter) {
    setSnapshotLoading(true)
    try {
      setSnapshots(await listSnapshotHistory(status))
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to load snapshot history: ${error?.message || 'unknown error'}` })
    } finally {
      setSnapshotLoading(false)
    }
  }

  async function runSnapshotAudit() {
    setSnapshotLoading(true)
    setNotice(null)
    try {
      const result = await auditSnapshotHistory()
      setSnapshotAudit(result)
      if (snapshotFilter !== 'all') setSnapshotFilter('all')
      else await fetchSnapshots('all')
      setNotice({
        type: 'success',
        text: result.candidate_count > 0
          ? `Audit completed: ${result.candidate_count} candidate snapshot(s) found. No data was changed.`
          : `Audit completed: ${result.scanned} snapshot(s) checked and no anomalies found.`,
      })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Snapshot audit failed: ${error?.message || 'unknown error'}` })
    } finally {
      setSnapshotLoading(false)
    }
  }

  async function markSnapshotInvalid(row: SnapshotAdminRow) {
    const suggested = candidateById.get(row.id)?.anomaly?.suggested_reason || 'manual_review'
    const reason = window.prompt('Reason for marking this snapshot invalid:', suggested)
    if (reason === null) return
    setSnapshotLoading(true)
    setNotice(null)
    try {
      await updateSnapshotValidity(row.id, false, reason.trim() || suggested)
      setSnapshotAudit((previous) => {
        if (!previous) return previous
        const candidates = previous.candidates.filter((candidate) => candidate.id !== row.id)
        return { ...previous, candidates, candidate_count: candidates.length }
      })
      await fetchSnapshots(snapshotFilter)
      setNotice({ type: 'success', text: 'Snapshot marked invalid and removed from portfolio history.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to update snapshot: ${error?.message || 'unknown error'}` })
    } finally {
      setSnapshotLoading(false)
    }
  }

  async function restoreSnapshot(row: SnapshotAdminRow) {
    if (!window.confirm(`Restore snapshot ${new Date(row.timestamp).toLocaleString()} to portfolio history?`)) return
    setSnapshotLoading(true)
    setNotice(null)
    try {
      await updateSnapshotValidity(row.id, true)
      await fetchSnapshots(snapshotFilter)
      setNotice({ type: 'success', text: 'Snapshot restored to portfolio history.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to restore snapshot: ${error?.message || 'unknown error'}` })
    } finally {
      setSnapshotLoading(false)
    }
  }

  async function quarantineAuditCandidates() {
    const candidates = snapshotAudit?.candidates.filter((row) => row.is_valid) || []
    if (candidates.length === 0) return
    if (!window.confirm(`Mark ${candidates.length} detected snapshot(s) invalid? This is reversible.`)) return
    setSnapshotLoading(true)
    setNotice(null)
    try {
      for (const row of candidates) {
        await updateSnapshotValidity(row.id, false, row.anomaly?.suggested_reason || 'audit_anomaly')
      }
      setSnapshotAudit(null)
      await fetchSnapshots(snapshotFilter)
      setNotice({ type: 'success', text: `${candidates.length} snapshot(s) moved to quarantine.` })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to quarantine snapshots: ${error?.message || 'unknown error'}` })
    } finally {
      setSnapshotLoading(false)
    }
  }

  const candidateById = React.useMemo(
    () => new Map((snapshotAudit?.candidates || []).map((row) => [row.id, row])),
    [snapshotAudit]
  )

  async function addMapping(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setNotice(null)
    try {
      await createPriceSymbolMapping(toPayload(newMapping))
      setNewMapping(EMPTY_FORM)
      await fetchMappings()
      setNotice({ type: 'success', text: 'Price mapping added successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to add price mapping: ${error?.message || 'unknown error'}` })
    }
  }

  async function saveMapping(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!editingSymbol) return
    setNotice(null)
    try {
      await updatePriceSymbolMapping(editingSymbol, toPayload(editingMapping))
      setEditingSymbol(null)
      setEditingMapping(EMPTY_FORM)
      await fetchMappings()
      setNotice({ type: 'success', text: 'Price mapping updated successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to update price mapping: ${error?.message || 'unknown error'}` })
    }
  }

  async function removeMapping(symbol: string) {
    setNotice(null)
    if (!window.confirm(`Delete price mapping for ${symbol}?`)) return
    try {
      await deletePriceSymbolMapping(symbol)
      if (editingSymbol === symbol) {
        setEditingSymbol(null)
        setEditingMapping(EMPTY_FORM)
      }
      await fetchMappings()
      setNotice({ type: 'success', text: 'Price mapping deleted successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to delete price mapping: ${error?.message || 'unknown error'}` })
    }
  }

  const renderMappingFields = (form: MappingForm, setForm: React.Dispatch<React.SetStateAction<MappingForm>>, disabled = false) => (
    <Grid container spacing={1.5} alignItems="center">
      <Grid item xs={12} md={1.4}>
        <TextField
          label="Symbol"
          value={form.symbol}
          onChange={(e) => setForm((prev) => ({ ...prev, symbol: e.target.value.toUpperCase() }))}
          fullWidth
          required
          size="small"
          disabled={disabled}
        />
      </Grid>
      <Grid item xs={12} md={2.4}>
        <TextField
          label="CoinGecko ID"
          value={form.provider_id}
          onChange={(e) => setForm((prev) => ({ ...prev, provider_id: e.target.value }))}
          fullWidth
          required
          size="small"
          disabled={disabled}
        />
      </Grid>
      <Grid item xs={12} md={2.2}>
        <TextField
          label="Label"
          value={form.label}
          onChange={(e) => setForm((prev) => ({ ...prev, label: e.target.value }))}
          fullWidth
          size="small"
          disabled={disabled}
        />
      </Grid>
      <Grid item xs={12} md={3}>
        <TextField
          label="Notes"
          value={form.notes}
          onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
          fullWidth
          size="small"
          disabled={disabled}
        />
      </Grid>
      <Grid item xs={6} md={1}>
        <Tooltip title="Enabled">
          <Checkbox
            checked={form.enabled}
            onChange={(e) => setForm((prev) => ({ ...prev, enabled: e.target.checked }))}
            disabled={disabled}
          />
        </Tooltip>
      </Grid>
      <Grid item xs={6} md={2}>
        <Button type="submit" variant="contained" fullWidth disabled={disabled || loading} startIcon={<AddRoundedIcon />}>
          Add
        </Button>
      </Grid>
    </Grid>
  )

  return (
    <Stack spacing={2}>
      {notice ? <Alert severity={notice.type}>{notice.text}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          <Stack spacing={2}>
            <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1.5}>
              <Box>
                <Typography variant="h6">Snapshot History</Typography>
                <Typography variant="body2" color="text.secondary">
                  Review portfolio snapshots and quarantine invalid points without deleting them.
                </Typography>
              </Box>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
                <Button variant="outlined" onClick={runSnapshotAudit} disabled={snapshotLoading}>
                  Run audit
                </Button>
                {snapshotAudit && snapshotAudit.candidate_count > 0 ? (
                  <Button color="warning" variant="contained" onClick={quarantineAuditCandidates} disabled={snapshotLoading}>
                    Quarantine detected ({snapshotAudit.candidate_count})
                  </Button>
                ) : null}
              </Stack>
            </Stack>

            <ButtonGroup size="small" aria-label="Snapshot status filter">
              {(['all', 'valid', 'invalid'] as SnapshotFilter[]).map((status) => (
                <Button
                  key={status}
                  variant={snapshotFilter === status ? 'contained' : 'outlined'}
                  onClick={() => setSnapshotFilter(status)}
                >
                  {status === 'all' ? 'All' : status === 'valid' ? 'Valid' : 'Invalid'}
                </Button>
              ))}
            </ButtonGroup>

            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ tableLayout: 'fixed', minWidth: 900, width: '100%' }}>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ width: '17%' }}>Date</TableCell>
                    <TableCell sx={{ width: '16%' }}>Total EUR</TableCell>
                    <TableCell sx={{ width: '16%' }}>Total USD</TableCell>
                    <TableCell sx={{ width: '11%' }}>Status</TableCell>
                    <TableCell sx={{ width: '25%' }}>Reason / Audit</TableCell>
                    <TableCell
                      align="right"
                      sx={{
                        width: '15%',
                        position: 'sticky',
                        right: 0,
                        zIndex: 2,
                        bgcolor: 'background.paper',
                        boxShadow: '-8px 0 12px -12px rgba(0,0,0,0.45)',
                      }}
                    >
                      Actions
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {snapshots.map((row) => {
                    const candidate = candidateById.get(row.id)
                    return (
                      <TableRow key={row.id} sx={candidate ? { bgcolor: 'warning.light' } : undefined}>
                        <TableCell sx={{ whiteSpace: 'nowrap' }}>{new Date(row.timestamp).toLocaleString()}</TableCell>
                        <TableCell sx={{ overflow: 'hidden' }}>
                          <Tooltip title={snapshotTotalDetails(row.total_eur, 'EUR')}>
                            <Typography variant="body2" noWrap>
                              {formatSnapshotTotal(row.total_eur, 'EUR')}
                            </Typography>
                          </Tooltip>
                        </TableCell>
                        <TableCell sx={{ overflow: 'hidden' }}>
                          <Tooltip title={snapshotTotalDetails(row.total_usd, 'USD')}>
                            <Typography variant="body2" noWrap>
                              {formatSnapshotTotal(row.total_usd, 'USD')}
                            </Typography>
                          </Tooltip>
                        </TableCell>
                        <TableCell>
                          <Chip
                            size="small"
                            color={row.is_valid ? (candidate ? 'warning' : 'success') : 'error'}
                            variant="outlined"
                            label={row.is_valid ? (candidate ? 'Candidate' : 'Valid') : 'Invalid'}
                          />
                        </TableCell>
                        <TableCell sx={{ overflow: 'hidden' }}>
                          <Tooltip
                            title={row.invalid_reason || candidate?.anomaly?.detected_reasons.join(', ') || '-'}
                          >
                            <Typography variant="body2" noWrap>
                              {row.invalid_reason
                                || candidate?.anomaly?.detected_reasons.join(', ')
                                || '-'}
                            </Typography>
                          </Tooltip>
                        </TableCell>
                        <TableCell
                          align="right"
                          sx={{
                            position: 'sticky',
                            right: 0,
                            zIndex: 1,
                            bgcolor: 'background.paper',
                            boxShadow: '-8px 0 12px -12px rgba(0,0,0,0.45)',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {row.is_valid ? (
                            <Button size="small" color="warning" onClick={() => markSnapshotInvalid(row)} disabled={snapshotLoading}>
                              Mark invalid
                            </Button>
                          ) : (
                            <Button size="small" onClick={() => restoreSnapshot(row)} disabled={snapshotLoading}>
                              Restore
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    )
                  })}
                  {snapshots.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={6}>
                        <Typography color="text.secondary">
                          {snapshotLoading ? 'Loading snapshots…' : 'No snapshots found for this filter.'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>
          </Stack>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Price Mappings</Typography>

          <Box component="form" onSubmit={addMapping} sx={{ mb: 2.5 }}>
            {renderMappingFields(newMapping, setNewMapping, loading)}
          </Box>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell>CoinGecko ID</TableCell>
                <TableCell>Label</TableCell>
                <TableCell>Enabled</TableCell>
                <TableCell>Notes</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {mappings.map((row) => {
                const isEditing = editingSymbol === row.symbol
                return (
                  <TableRow key={row.symbol}>
                    {isEditing ? (
                      <TableCell colSpan={6}>
                        <Box component="form" onSubmit={saveMapping}>
                          <Grid container spacing={1.5} alignItems="center">
                            <Grid item xs={12} md={1.4}>
                              <TextField label="Symbol" value={editingMapping.symbol} onChange={(e) => setEditingMapping((prev) => ({ ...prev, symbol: e.target.value.toUpperCase() }))} fullWidth required size="small" />
                            </Grid>
                            <Grid item xs={12} md={2.4}>
                              <TextField label="CoinGecko ID" value={editingMapping.provider_id} onChange={(e) => setEditingMapping((prev) => ({ ...prev, provider_id: e.target.value }))} fullWidth required size="small" />
                            </Grid>
                            <Grid item xs={12} md={2.2}>
                              <TextField label="Label" value={editingMapping.label} onChange={(e) => setEditingMapping((prev) => ({ ...prev, label: e.target.value }))} fullWidth size="small" />
                            </Grid>
                            <Grid item xs={12} md={3}>
                              <TextField label="Notes" value={editingMapping.notes} onChange={(e) => setEditingMapping((prev) => ({ ...prev, notes: e.target.value }))} fullWidth size="small" />
                            </Grid>
                            <Grid item xs={4} md={1}>
                              <Checkbox checked={editingMapping.enabled} onChange={(e) => setEditingMapping((prev) => ({ ...prev, enabled: e.target.checked }))} />
                            </Grid>
                            <Grid item xs={8} md={2}>
                              <Stack direction="row" spacing={1} justifyContent="flex-end">
                                <Tooltip title="Save">
                                  <IconButton type="submit" color="primary" disabled={loading}><SaveRoundedIcon /></IconButton>
                                </Tooltip>
                                <Tooltip title="Cancel">
                                  <IconButton onClick={() => setEditingSymbol(null)}><CloseRoundedIcon /></IconButton>
                                </Tooltip>
                              </Stack>
                            </Grid>
                          </Grid>
                        </Box>
                      </TableCell>
                    ) : (
                      <>
                        <TableCell><Typography fontWeight={700}>{row.symbol}</Typography></TableCell>
                        <TableCell>{row.provider_id}</TableCell>
                        <TableCell>{row.label || '-'}</TableCell>
                        <TableCell>{row.enabled ? 'Yes' : 'No'}</TableCell>
                        <TableCell>{row.notes || '-'}</TableCell>
                        <TableCell align="right">
                          <Tooltip title="Edit">
                            <IconButton size="small" onClick={() => { setEditingSymbol(row.symbol); setEditingMapping(toForm(row)) }}>
                              <EditRoundedIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          <Tooltip title="Delete">
                            <IconButton size="small" color="error" onClick={() => removeMapping(row.symbol)}>
                              <DeleteOutlineRoundedIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </>
                    )}
                  </TableRow>
                )
              })}
              {mappings.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography color="text.secondary">No price mappings configured.</Typography>
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Stack>
  )
}
