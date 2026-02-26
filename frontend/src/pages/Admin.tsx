import React from 'react'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import CloseRoundedIcon from '@mui/icons-material/CloseRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import EditRoundedIcon from '@mui/icons-material/EditRounded'
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded'
import SaveRoundedIcon from '@mui/icons-material/SaveRounded'
import { Alert, Box, Button, Card, CardContent, Divider, Grid, List, ListItem, ListItemText, MenuItem, Stack, TextField, Typography } from '@mui/material'
import {
  createBinanceAccount,
  createWallet,
  deleteBinanceAccount,
  deleteWallet,
  listBinanceAccounts,
  listWallets,
  updateBinanceAccount,
  updateWallet,
} from '../shared/api'

type Notice = { type: 'success' | 'error'; text: string } | null
type WalletType = 'auto' | 'ethereum' | 'bitcoin' | 'solana'

function walletTypeLabel(raw: any): string {
  const t = String(raw || '').toLowerCase()
  if (t === 'bitcoin') return 'Bitcoin'
  if (t === 'solana') return 'Solana'
  return 'ETH'
}

export default function Admin() {
  const [accounts, setAccounts] = React.useState<any[]>([])
  const [wallets, setWallets] = React.useState<any[]>([])
  const [editingAccountId, setEditingAccountId] = React.useState<number | null>(null)
  const [editingWalletId, setEditingWalletId] = React.useState<number | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [notice, setNotice] = React.useState<Notice>(null)

  React.useEffect(() => {
    fetchAll()
  }, [])

  async function fetchAll() {
    setLoading(true)
    try {
      const [accountRows, walletRows] = await Promise.all([listBinanceAccounts(), listWallets()])
      setAccounts(accountRows)
      setWallets(walletRows)
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to load admin data: ${error?.message || 'unknown error'}` })
    } finally {
      setLoading(false)
    }
  }

  async function addAccount(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setNotice(null)
    const form = e.currentTarget
    const f = new FormData(form)
    const identifier = String(f.get('identifier') || '').trim()
    const apiKey = String(f.get('api_key') || '').trim()
    const apiSecret = String(f.get('api_secret') || '').trim()

    if (!identifier || !apiKey || !apiSecret) {
      setNotice({ type: 'error', text: 'Please fill in identifier, API key, and API secret.' })
      return
    }

    try {
      await createBinanceAccount({
        identifier,
        label: String(f.get('label') || '').trim() || null,
        api_key: apiKey,
        api_secret: apiSecret,
      })
      form.reset()
      await fetchAll()
      setNotice({ type: 'success', text: 'Binance account added successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to add Binance account: ${error?.message || 'unknown error'}` })
    }
  }

  async function addWallet(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setNotice(null)
    const form = e.currentTarget
    const f = new FormData(form)
    const identifier = String(f.get('identifier') || '').trim()
    const walletType = String(f.get('wallet_type') || 'auto').trim().toLowerCase() as WalletType
    if (!identifier) {
      setNotice({ type: 'error', text: 'Please fill in the wallet address.' })
      return
    }

    try {
      await createWallet({
        identifier,
        wallet_type: walletType === 'auto' ? null : walletType,
        label: String(f.get('label') || '').trim() || null,
      })
      form.reset()
      await fetchAll()
      setNotice({ type: 'success', text: 'Wallet added successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to add wallet: ${error?.message || 'unknown error'}` })
    }
  }

  async function saveAccountEdit(e: React.FormEvent<HTMLFormElement>, accountId: number) {
    e.preventDefault()
    setNotice(null)
    const form = e.currentTarget
    const f = new FormData(form)
    const identifier = String(f.get('identifier') || '').trim()
    if (!identifier) {
      setNotice({ type: 'error', text: 'Identifier is required.' })
      return
    }

    try {
      await updateBinanceAccount(accountId, {
        identifier,
        label: String(f.get('label') || '').trim() || null,
        api_key: String(f.get('api_key') || '').trim() || null,
        api_secret: String(f.get('api_secret') || '').trim() || null,
      })
      setEditingAccountId(null)
      await fetchAll()
      setNotice({ type: 'success', text: 'Binance account updated successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to update Binance account: ${error?.message || 'unknown error'}` })
    }
  }

  async function removeAccount(accountId: number) {
    setNotice(null)
    if (!window.confirm('Delete this Binance account?')) return
    try {
      await deleteBinanceAccount(accountId)
      if (editingAccountId === accountId) setEditingAccountId(null)
      await fetchAll()
      setNotice({ type: 'success', text: 'Binance account deleted successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to delete Binance account: ${error?.message || 'unknown error'}` })
    }
  }

  async function saveWalletEdit(e: React.FormEvent<HTMLFormElement>, walletId: number) {
    e.preventDefault()
    setNotice(null)
    const form = e.currentTarget
    const f = new FormData(form)
    const identifier = String(f.get('identifier') || '').trim()
    const walletType = String(f.get('wallet_type') || 'auto').trim().toLowerCase() as WalletType
    if (!identifier) {
      setNotice({ type: 'error', text: 'Wallet address is required.' })
      return
    }

    try {
      await updateWallet(walletId, {
        identifier,
        wallet_type: walletType === 'auto' ? null : walletType,
        label: String(f.get('label') || '').trim() || null,
      })
      setEditingWalletId(null)
      await fetchAll()
      setNotice({ type: 'success', text: 'Wallet updated successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to update wallet: ${error?.message || 'unknown error'}` })
    }
  }

  async function removeWallet(walletId: number) {
    setNotice(null)
    if (!window.confirm('Delete this wallet?')) return
    try {
      await deleteWallet(walletId)
      if (editingWalletId === walletId) setEditingWalletId(null)
      await fetchAll()
      setNotice({ type: 'success', text: 'Wallet deleted successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to delete wallet: ${error?.message || 'unknown error'}` })
    }
  }

  return (
    <Stack spacing={2}>
      {notice ? <Alert severity={notice.type}>{notice.text}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
            <Typography variant="h6">Binance Accounts</Typography>
            <Button variant="outlined" onClick={fetchAll} disabled={loading} startIcon={<RefreshRoundedIcon />}>
              {loading ? 'Loading...' : 'Refresh'}
            </Button>
          </Stack>

          <Box component="form" onSubmit={addAccount}>
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
              Add New Binance Account
            </Typography>
            <Grid container spacing={1.5}>
              <Grid item xs={12} md={2}>
                <TextField name="identifier" label="Identifier" fullWidth required size="small" />
              </Grid>
              <Grid item xs={12} md={2}>
                <TextField name="label" label="Label (optional)" fullWidth size="small" />
              </Grid>
              <Grid item xs={12} md={3}>
                <TextField name="api_key" label="API Key" fullWidth required size="small" />
              </Grid>
              <Grid item xs={12} md={3}>
                <TextField name="api_secret" label="API Secret" fullWidth required size="small" />
              </Grid>
              <Grid item xs={12} md={2}>
                <Button type="submit" variant="contained" fullWidth disabled={loading} startIcon={<AddRoundedIcon />}>
                  Add
                </Button>
              </Grid>
            </Grid>
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
            Existing Binance Accounts
          </Typography>
          <List dense>
            {accounts.length === 0 ? <ListItem><ListItemText primary="No Binance accounts registered." /></ListItem> : null}
            {accounts.map((a) => (
              <ListItem
                key={a.id}
                divider
                sx={{
                  alignItems: 'flex-start',
                  py: editingAccountId === a.id ? 4 : 1,
                }}
              >
                {editingAccountId === a.id ? (
                  <Box component="form" onSubmit={(e) => saveAccountEdit(e, a.id)} sx={{ width: '100%' }}>
                    <Grid container spacing={1.5} alignItems="flex-start">
                      <Grid item xs={12} md={2}>
                        <TextField name="identifier" label="Identifier" defaultValue={a.identifier || ''} required size="small" fullWidth />
                      </Grid>
                      <Grid item xs={12} md={2}>
                        <TextField name="label" label="Label" defaultValue={a.label || ''} size="small" fullWidth />
                      </Grid>
                      <Grid item xs={12} md={3}>
                        <TextField
                          name="api_key"
                          label="API Key"
                          placeholder={a.api_key_masked || '********'}
                          helperText="Leave empty to keep current key"
                          size="small"
                          fullWidth
                        />
                      </Grid>
                      <Grid item xs={12} md={3}>
                        <TextField
                          name="api_secret"
                          label="API Secret"
                          placeholder={a.api_secret_masked || '********'}
                          helperText="Leave empty to keep current secret"
                          size="small"
                          fullWidth
                        />
                      </Grid>
                      <Grid item xs={12} md={2}>
                        <Stack direction="row" spacing={1} justifyContent="flex-end">
                          <Button type="submit" variant="contained" size="small" startIcon={<SaveRoundedIcon />}>Save</Button>
                          <Button variant="outlined" size="small" onClick={() => setEditingAccountId(null)} startIcon={<CloseRoundedIcon />}>Cancel</Button>
                        </Stack>
                      </Grid>
                    </Grid>
                  </Box>
                ) : (
                  <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={1}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', md: 'center' }}
                    sx={{ width: '100%' }}
                  >
                    <ListItemText
                      primary={a.identifier}
                      secondary={
                        <>
                          <span>{a.label || 'no label'}</span>
                          <br />
                          <span>API key: {a.api_key_masked || '********'}</span>
                        </>
                      }
                    />
                    <Stack direction="row" spacing={1}>
                      <Button size="small" variant="outlined" onClick={() => setEditingAccountId(a.id)} startIcon={<EditRoundedIcon />}>Edit</Button>
                      <Button size="small" color="error" variant="outlined" onClick={() => removeAccount(a.id)} startIcon={<DeleteOutlineRoundedIcon />}>Delete</Button>
                    </Stack>
                  </Stack>
                )}
              </ListItem>
            ))}
          </List>
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Wallets</Typography>
          <Box component="form" onSubmit={addWallet}>
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
              Add New Wallet
            </Typography>
            <Grid container spacing={1.5}>
              <Grid item xs={12} md={3}>
                <TextField name="identifier" label="Wallet Address" fullWidth required size="small" />
              </Grid>
              <Grid item xs={12} md={2}>
                <TextField
                  name="wallet_type"
                  label="Wallet Type"
                  defaultValue="auto"
                  select
                  fullWidth
                  size="small"
                >
                  <MenuItem value="auto">Auto</MenuItem>
                  <MenuItem value="ethereum">ETH</MenuItem>
                  <MenuItem value="bitcoin">Bitcoin</MenuItem>
                  <MenuItem value="solana">Solana</MenuItem>
                </TextField>
              </Grid>
              <Grid item xs={12} md={5}>
                <TextField name="label" label="Label (optional)" fullWidth size="small" />
              </Grid>
              <Grid item xs={12} md={2}>
                <Button type="submit" variant="contained" fullWidth disabled={loading} startIcon={<AddRoundedIcon />}>
                  Add Wallet
                </Button>
              </Grid>
            </Grid>
          </Box>

          <Divider sx={{ my: 2 }} />

          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
            Existing Wallets
          </Typography>
          <List dense>
            {wallets.length === 0 ? <ListItem><ListItemText primary="No wallets registered." /></ListItem> : null}
            {wallets.map((w) => (
              <ListItem
                key={w.id}
                divider
                sx={{
                  alignItems: 'flex-start',
                  py: editingWalletId === w.id ? 4 : 1,
                }}
              >
                {editingWalletId === w.id ? (
                  <Box component="form" onSubmit={(e) => saveWalletEdit(e, w.id)} sx={{ width: '100%' }}>
                    <Grid container spacing={1.5} alignItems="center">
                      <Grid item xs={12} md={4}>
                        <TextField name="identifier" label="Wallet Address" defaultValue={w.identifier || ''} required size="small" fullWidth />
                      </Grid>
                      <Grid item xs={12} md={2}>
                        <TextField
                          name="wallet_type"
                          label="Wallet Type"
                          defaultValue={String(w.wallet_type || 'auto').toLowerCase()}
                          select
                          size="small"
                          fullWidth
                        >
                          <MenuItem value="auto">Auto</MenuItem>
                          <MenuItem value="ethereum">ETH</MenuItem>
                          <MenuItem value="bitcoin">Bitcoin</MenuItem>
                          <MenuItem value="solana">Solana</MenuItem>
                        </TextField>
                      </Grid>
                      <Grid item xs={12} md={3}>
                        <TextField name="label" label="Label" defaultValue={w.label || ''} size="small" fullWidth />
                      </Grid>
                      <Grid item xs={12} md={3}>
                        <Stack direction="row" spacing={1} justifyContent="flex-end">
                          <Button type="submit" variant="contained" size="small" startIcon={<SaveRoundedIcon />}>Save</Button>
                          <Button variant="outlined" size="small" onClick={() => setEditingWalletId(null)} startIcon={<CloseRoundedIcon />}>Cancel</Button>
                        </Stack>
                      </Grid>
                    </Grid>
                  </Box>
                ) : (
                  <Stack
                    direction={{ xs: 'column', md: 'row' }}
                    spacing={1}
                    justifyContent="space-between"
                    alignItems={{ xs: 'flex-start', md: 'center' }}
                    sx={{ width: '100%' }}
                  >
                    <ListItemText
                      primary={w.identifier}
                      secondary={
                        <>
                          <span>{w.label || 'no label'}</span>
                          <br />
                          <span>Wallet Type: {walletTypeLabel(w.wallet_type)}</span>
                        </>
                      }
                    />
                    <Stack direction="row" spacing={1}>
                      <Button size="small" variant="outlined" onClick={() => setEditingWalletId(w.id)} startIcon={<EditRoundedIcon />}>Edit</Button>
                      <Button size="small" color="error" variant="outlined" onClick={() => removeWallet(w.id)} startIcon={<DeleteOutlineRoundedIcon />}>Delete</Button>
                    </Stack>
                  </Stack>
                )}
              </ListItem>
            ))}
          </List>
        </CardContent>
      </Card>
    </Stack>
  )
}
