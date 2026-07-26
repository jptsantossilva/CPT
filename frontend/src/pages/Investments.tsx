import React from 'react'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import EditRoundedIcon from '@mui/icons-material/EditRounded'
import SaveRoundedIcon from '@mui/icons-material/SaveRounded'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Grid,
  MenuItem,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material'
import {
  createFiatCashFlow,
  deleteFiatCashFlow,
  fetchPortfolioPerformance,
  listFiatCashFlows,
  updateFiatCashFlow,
  type CurrencyPerformance,
  type FiatCashFlow,
  type FiatCashFlowPayload,
  type PortfolioPerformance,
} from '../shared/api'
import { formatEur, formatUsd } from '../shared/format'

type CurrencyMode = 'EUR' | 'USD'
type Notice = { type: 'success' | 'error'; text: string } | null
type FlowForm = {
  flow_type: 'deposit' | 'withdrawal'
  occurred_on: string
  original_currency: CurrencyMode
  original_amount: string
  counter_amount: string
  counterparty_type: 'bank' | 'person'
  counterparty_name: string
  notes: string
}

function today(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function emptyForm(currency: CurrencyMode): FlowForm {
  return {
    flow_type: 'deposit',
    occurred_on: today(),
    original_currency: currency,
    original_amount: '',
    counter_amount: '',
    counterparty_type: 'bank',
    counterparty_name: '',
    notes: '',
  }
}

function toPayload(form: FlowForm): FiatCashFlowPayload {
  return {
    flow_type: form.flow_type,
    occurred_on: form.occurred_on,
    original_currency: form.original_currency,
    original_amount: form.original_amount.trim(),
    counter_amount: form.counter_amount.trim(),
    counterparty_type: form.counterparty_type,
    counterparty_name: form.counterparty_name.trim(),
    notes: form.notes.trim() || null,
  }
}

function toForm(row: FiatCashFlow): FlowForm {
  return {
    flow_type: row.flow_type,
    occurred_on: row.occurred_on,
    original_currency: row.original_currency,
    original_amount: row.original_amount,
    counter_amount: row.counter_amount,
    counterparty_type: row.counterparty_type,
    counterparty_name: row.counterparty_name,
    notes: row.notes || '',
  }
}

function formatMoney(value: string | number | null, currency: CurrencyMode): string {
  if (value == null) return 'n/a'
  const amount = Number(value)
  return currency === 'EUR' ? formatEur(amount) : formatUsd(amount)
}

function formatDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString('en-GB')
}

function selectedPerformance(
  performance: PortfolioPerformance | null,
  currency: CurrencyMode,
): CurrencyPerformance | null {
  if (!performance) return null
  return currency === 'EUR' ? performance.eur : performance.usd
}

export default function Investments({ currencyMode }: { currencyMode: CurrencyMode }) {
  const [rows, setRows] = React.useState<FiatCashFlow[]>([])
  const [performance, setPerformance] = React.useState<PortfolioPerformance | null>(null)
  const [form, setForm] = React.useState<FlowForm>(() => emptyForm(currencyMode))
  const [editingId, setEditingId] = React.useState<number | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [notice, setNotice] = React.useState<Notice>(null)
  const [typeFilter, setTypeFilter] = React.useState<'all' | 'deposit' | 'withdrawal'>('all')
  const [partyFilter, setPartyFilter] = React.useState<'all' | 'bank' | 'person'>('all')
  const [nameFilter, setNameFilter] = React.useState('')

  const summary = selectedPerformance(performance, currencyMode)
  const pendingSummary = performance
    ? (currencyMode === 'EUR' ? performance.pending.eur : performance.pending.usd)
    : null
  const counterpartCurrency = form.original_currency === 'EUR' ? 'USD' : 'EUR'

  async function refresh() {
    setLoading(true)
    try {
      const [cashFlows, nextPerformance] = await Promise.all([
        listFiatCashFlows(),
        fetchPortfolioPerformance(),
      ])
      setRows(cashFlows)
      setPerformance(nextPerformance)
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to load investments: ${error?.message || 'unknown error'}` })
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    refresh()
  }, [])

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setNotice(null)
    try {
      if (editingId == null) {
        await createFiatCashFlow(toPayload(form))
        setNotice({ type: 'success', text: 'FIAT cash flow added.' })
      } else {
        await updateFiatCashFlow(editingId, toPayload(form))
        setNotice({ type: 'success', text: 'FIAT cash flow updated.' })
      }
      setEditingId(null)
      setForm(emptyForm(currencyMode))
      await refresh()
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to save cash flow: ${error?.message || 'unknown error'}` })
    }
  }

  function startEdit(row: FiatCashFlow) {
    setEditingId(row.id)
    setForm(toForm(row))
    setNotice(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function cancelEdit() {
    setEditingId(null)
    setForm(emptyForm(currencyMode))
  }

  async function remove(row: FiatCashFlow) {
    if (!window.confirm(`Delete the ${row.flow_type} from ${formatDate(row.occurred_on)}?`)) return
    setNotice(null)
    try {
      await deleteFiatCashFlow(row.id)
      if (editingId === row.id) cancelEdit()
      await refresh()
      setNotice({ type: 'success', text: 'FIAT cash flow deleted.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to delete cash flow: ${error?.message || 'unknown error'}` })
    }
  }

  const filteredRows = React.useMemo(() => {
    const query = nameFilter.trim().toLowerCase()
    return rows.filter((row) => {
      if (typeFilter !== 'all' && row.flow_type !== typeFilter) return false
      if (partyFilter !== 'all' && row.counterparty_type !== partyFilter) return false
      if (query && !row.counterparty_name.toLowerCase().includes(query)) return false
      return true
    })
  }, [nameFilter, partyFilter, rows, typeFilter])

  const hasWithdrawals = Number(summary?.withdrawals || 0) > 0
  const pnlLabel = hasWithdrawals ? 'Global PnL' : 'Unrealized PnL'
  const statusColor = summary?.status === 'gain'
    ? 'success.main'
    : summary?.status === 'loss'
      ? 'error.main'
      : 'text.primary'

  const cards = [
    { label: 'FIAT Added', value: summary?.deposits },
    { label: 'FIAT Withdrawn', value: summary?.withdrawals },
    { label: 'Net Invested', value: summary?.net_invested },
    { label: 'Current Portfolio', value: summary?.current_portfolio },
    { label: pnlLabel, value: summary?.pnl, color: statusColor },
  ]

  return (
    <Stack spacing={2}>
      {notice ? <Alert severity={notice.type}>{notice.text}</Alert> : null}

      {!performance?.snapshot ? (
        <Alert severity="info">
          Run a portfolio sync before calculating PnL. Recorded cash flows remain pending until a snapshot exists.
        </Alert>
      ) : null}
      {performance && performance.pending.count > 0 ? (
        <Alert severity="warning">
          {performance.pending.count} cash flow(s), totalling {formatMoney(pendingSummary?.net_invested || '0', currencyMode)} net,
          are later than the latest snapshot and excluded from PnL. Run a new sync to include them.
        </Alert>
      ) : null}

      <Grid container spacing={2}>
        {cards.map((card) => (
          <Grid item xs={12} sm={6} lg={2.4} key={card.label}>
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent>
                <Typography variant="overline" color="text.secondary">{card.label}</Typography>
                <Typography variant="h5" sx={{ fontWeight: 700, color: card.color || 'text.primary' }}>
                  {formatMoney(card.value ?? null, currencyMode)}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Card variant="outlined">
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={1} sx={{ mb: 2 }}>
            <Box>
              <Typography variant="h6">{editingId == null ? 'Add FIAT Cash Flow' : 'Edit FIAT Cash Flow'}</Typography>
              <Typography variant="body2" color="text.secondary">
                Use the historical EUR/USD equivalent shown by your bank or exchange for that date.
              </Typography>
            </Box>
            {performance?.snapshot?.timestamp ? (
              <Typography variant="body2" color="text.secondary">
                PnL snapshot: {new Date(performance.snapshot.timestamp).toLocaleString('en-GB')}
              </Typography>
            ) : null}
          </Stack>

          <Box component="form" onSubmit={submit}>
            <Grid container spacing={1.5}>
              <Grid item xs={12} sm={6} md={2}>
                <TextField
                  select
                  label="Type"
                  value={form.flow_type}
                  onChange={(e) => setForm((prev) => ({ ...prev, flow_type: e.target.value as FlowForm['flow_type'] }))}
                  fullWidth
                  size="small"
                >
                  <MenuItem value="deposit">Added to crypto</MenuItem>
                  <MenuItem value="withdrawal">Withdrawn to FIAT</MenuItem>
                </TextField>
              </Grid>
              <Grid item xs={12} sm={6} md={2}>
                <TextField
                  type="date"
                  label="Date"
                  value={form.occurred_on}
                  onChange={(e) => setForm((prev) => ({ ...prev, occurred_on: e.target.value }))}
                  inputProps={{ max: today() }}
                  InputLabelProps={{ shrink: true }}
                  required
                  fullWidth
                  size="small"
                />
              </Grid>
              <Grid item xs={12} sm={4} md={1.4}>
                <TextField
                  select
                  label="Currency"
                  value={form.original_currency}
                  onChange={(e) => setForm((prev) => ({
                    ...prev,
                    original_currency: e.target.value as CurrencyMode,
                    original_amount: '',
                    counter_amount: '',
                  }))}
                  fullWidth
                  size="small"
                >
                  <MenuItem value="EUR">EUR</MenuItem>
                  <MenuItem value="USD">USD</MenuItem>
                </TextField>
              </Grid>
              <Grid item xs={12} sm={4} md={2}>
                <TextField
                  type="number"
                  label={`Amount (${form.original_currency})`}
                  value={form.original_amount}
                  onChange={(e) => setForm((prev) => ({ ...prev, original_amount: e.target.value }))}
                  inputProps={{ min: '0.01', step: '0.01' }}
                  required
                  fullWidth
                  size="small"
                />
              </Grid>
              <Grid item xs={12} sm={4} md={2}>
                <TextField
                  type="number"
                  label={`Equivalent (${counterpartCurrency})`}
                  value={form.counter_amount}
                  onChange={(e) => setForm((prev) => ({ ...prev, counter_amount: e.target.value }))}
                  inputProps={{ min: '0.01', step: '0.01' }}
                  required
                  fullWidth
                  size="small"
                />
              </Grid>
              <Grid item xs={12} sm={4} md={1.6}>
                <TextField
                  select
                  label={form.flow_type === 'deposit' ? 'Origin type' : 'Destination type'}
                  value={form.counterparty_type}
                  onChange={(e) => setForm((prev) => ({ ...prev, counterparty_type: e.target.value as FlowForm['counterparty_type'] }))}
                  fullWidth
                  size="small"
                >
                  <MenuItem value="bank">Bank</MenuItem>
                  <MenuItem value="person">Person</MenuItem>
                </TextField>
              </Grid>
              <Grid item xs={12} sm={8} md={3}>
                <TextField
                  label={form.counterparty_type === 'bank' ? 'Bank name' : 'Person name'}
                  value={form.counterparty_name}
                  onChange={(e) => setForm((prev) => ({ ...prev, counterparty_name: e.target.value }))}
                  inputProps={{ maxLength: 200 }}
                  required
                  fullWidth
                  size="small"
                />
              </Grid>
              <Grid item xs={12} md={7}>
                <TextField
                  label="Notes (optional)"
                  value={form.notes}
                  onChange={(e) => setForm((prev) => ({ ...prev, notes: e.target.value }))}
                  inputProps={{ maxLength: 1000 }}
                  fullWidth
                  size="small"
                />
              </Grid>
              <Grid item xs={12} md={2}>
                <Button
                  type="submit"
                  variant="contained"
                  startIcon={editingId == null ? <AddRoundedIcon /> : <SaveRoundedIcon />}
                  disabled={loading}
                  fullWidth
                >
                  {editingId == null ? 'Add' : 'Save'}
                </Button>
              </Grid>
              {editingId != null ? (
                <Grid item xs={12} md={2}>
                  <Button variant="outlined" startIcon={<CloseRoundedIcon />} onClick={cancelEdit} fullWidth>
                    Cancel
                  </Button>
                </Grid>
              ) : null}
            </Grid>
          </Box>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" sx={{ mb: 1.5 }}>FIAT Cash Flow History</Typography>
          <Grid container spacing={1.5} sx={{ mb: 2 }}>
            <Grid item xs={12} sm={4}>
              <TextField select label="Flow type" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value as typeof typeFilter)} fullWidth size="small">
                <MenuItem value="all">All types</MenuItem>
                <MenuItem value="deposit">Added</MenuItem>
                <MenuItem value="withdrawal">Withdrawn</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField select label="Counterparty type" value={partyFilter} onChange={(e) => setPartyFilter(e.target.value as typeof partyFilter)} fullWidth size="small">
                <MenuItem value="all">All counterparties</MenuItem>
                <MenuItem value="bank">Banks</MenuItem>
                <MenuItem value="person">People</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField label="Search name" value={nameFilter} onChange={(e) => setNameFilter(e.target.value)} fullWidth size="small" />
            </Grid>
          </Grid>
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Date</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Counterparty</TableCell>
                  <TableCell align="right">EUR</TableCell>
                  <TableCell align="right">USD</TableCell>
                  <TableCell>Notes</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredRows.length === 0 ? (
                  <TableRow><TableCell colSpan={7} align="center">No matching cash flows.</TableCell></TableRow>
                ) : null}
                {filteredRows.map((row) => (
                  <TableRow key={row.id} hover>
                    <TableCell>{formatDate(row.occurred_on)}</TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        label={row.flow_type === 'deposit' ? 'Added' : 'Withdrawn'}
                        color={row.flow_type === 'deposit' ? 'primary' : 'default'}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2">{row.counterparty_name}</Typography>
                      <Typography variant="caption" color="text.secondary">{row.counterparty_type}</Typography>
                    </TableCell>
                    <TableCell align="right">{formatEur(Number(row.amount_eur))}</TableCell>
                    <TableCell align="right">{formatUsd(Number(row.amount_usd))}</TableCell>
                    <TableCell>{row.notes || '—'}</TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={() => startEdit(row)} startIcon={<EditRoundedIcon />}>Edit</Button>
                      <Button size="small" color="error" onClick={() => remove(row)} startIcon={<DeleteOutlineRoundedIcon />}>Delete</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </CardContent>
      </Card>

      {performance && performance.by_counterparty.length > 0 ? (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h6">Cash Flows by Counterparty</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              These are cash-flow totals only; they do not allocate portfolio value or PnL to a bank or person.
            </Typography>
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Name</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell align="right">Added</TableCell>
                    <TableCell align="right">Withdrawn</TableCell>
                    <TableCell align="right">Net</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {performance.by_counterparty.map((party) => {
                    const values = currencyMode === 'EUR' ? party.eur : party.usd
                    return (
                      <TableRow key={`${party.counterparty_type}:${party.counterparty_name}`}>
                        <TableCell>{party.counterparty_name}</TableCell>
                        <TableCell>{party.counterparty_type}</TableCell>
                        <TableCell align="right">{formatMoney(values.deposits, currencyMode)}</TableCell>
                        <TableCell align="right">{formatMoney(values.withdrawals, currencyMode)}</TableCell>
                        <TableCell align="right">{formatMoney(values.net_invested, currencyMode)}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </Box>
          </CardContent>
        </Card>
      ) : null}

      <Alert severity="info">
        Global PnL equals current portfolio + FIAT withdrawn − FIAT added. Once withdrawals exist, realized and unrealized PnL cannot be separated without the cost basis of the assets sold.
      </Alert>
    </Stack>
  )
}
