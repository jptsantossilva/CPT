import React from 'react'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import EditRoundedIcon from '@mui/icons-material/EditRounded'
import SaveRoundedIcon from '@mui/icons-material/SaveRounded'
import { Alert, Box, Button, Card, CardContent, Checkbox, Grid, IconButton, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, Tooltip, Typography } from '@mui/material'
import {
  createPriceSymbolMapping,
  deletePriceSymbolMapping,
  listPriceSymbolMappings,
  type PriceSymbolMapping,
  updatePriceSymbolMapping,
} from '../shared/api'

type Notice = { type: 'success' | 'error'; text: string } | null
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

export default function Settings() {
  const [mappings, setMappings] = React.useState<PriceSymbolMapping[]>([])
  const [loading, setLoading] = React.useState(false)
  const [notice, setNotice] = React.useState<Notice>(null)
  const [newMapping, setNewMapping] = React.useState<MappingForm>(EMPTY_FORM)
  const [editingSymbol, setEditingSymbol] = React.useState<string | null>(null)
  const [editingMapping, setEditingMapping] = React.useState<MappingForm>(EMPTY_FORM)

  React.useEffect(() => {
    fetchMappings()
  }, [])

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
