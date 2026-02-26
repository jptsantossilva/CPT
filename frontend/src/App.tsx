import React from 'react'
import AccountBalanceWalletRoundedIcon from '@mui/icons-material/AccountBalanceWalletRounded'
import AdminPanelSettingsRoundedIcon from '@mui/icons-material/AdminPanelSettingsRounded'
import CollectionsRoundedIcon from '@mui/icons-material/CollectionsRounded'
import DarkModeRoundedIcon from '@mui/icons-material/DarkModeRounded'
import DashboardRoundedIcon from '@mui/icons-material/DashboardRounded'
import LightModeRoundedIcon from '@mui/icons-material/LightModeRounded'
import PaidRoundedIcon from '@mui/icons-material/PaidRounded'
import { Box, Button, CssBaseline, IconButton, Paper, Stack, ThemeProvider, Tooltip, Typography } from '@mui/material'
import Assets from './pages/Assets'
import Dashboard from './pages/Dashboard'
import Nfts from './pages/Nfts'
import { buildTheme, type AppMode } from './theme'

const AdminPage = React.lazy(() => import('./pages/Admin'))
type Theme = AppMode

export default function App(){
  const [route, setRoute] = React.useState<'dashboard'|'assets'|'nfts'|'admin'>('dashboard')
  const [theme, setTheme] = React.useState<Theme>(() => {
    const saved = window.localStorage.getItem('cpt_theme')
    if (saved === 'dark' || saved === 'light') return saved
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  })
  const navItems: Array<{ key: 'dashboard' | 'assets' | 'nfts' | 'admin'; label: string; icon: React.ReactNode }> = [
    { key: 'dashboard', label: 'Dashboard', icon: <DashboardRoundedIcon fontSize="small" /> },
    { key: 'assets', label: 'Coins', icon: <PaidRoundedIcon fontSize="small" /> },
    { key: 'nfts', label: 'NFTs', icon: <CollectionsRoundedIcon fontSize="small" /> },
    { key: 'admin', label: 'Admin', icon: <AdminPanelSettingsRoundedIcon fontSize="small" /> },
  ]
  const themeObj = React.useMemo(() => buildTheme(theme), [theme])

  React.useEffect(() => {
    window.localStorage.setItem('cpt_theme', theme)
  }, [theme])

  return (
    <ThemeProvider theme={themeObj}>
      <CssBaseline />
      <Box
        sx={{
          minHeight: '100vh',
          py: 3,
          px: 2,
          background: (t) =>
            t.palette.mode === 'dark'
              ? 'radial-gradient(1200px 500px at 0% -10%, rgba(91,141,239,0.18), transparent), radial-gradient(900px 400px at 100% -20%, rgba(255,152,0,0.16), transparent)'
              : 'radial-gradient(1200px 500px at 0% -10%, rgba(91,141,239,0.12), transparent), radial-gradient(900px 400px at 100% -20%, rgba(255,152,0,0.10), transparent)',
        }}
      >
        <Box sx={{ maxWidth: 1500, mx: 'auto' }}>
          <Paper
            variant="outlined"
            sx={{
              p: 2.5,
              mb: 2,
              backdropFilter: 'blur(8px)',
              background: (t) =>
                t.palette.mode === 'dark'
                  ? 'linear-gradient(135deg, rgba(17,24,45,0.88), rgba(13,19,37,0.92))'
                  : 'linear-gradient(135deg, rgba(255,255,255,0.92), rgba(248,251,255,0.94))',
            }}
          >
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }}>
              <Box>
                <Stack direction="row" spacing={1} alignItems="center">
                  <AccountBalanceWalletRoundedIcon color="primary" />
                  <Typography variant="h5">Crypto Portfolio Tracker</Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  Monitor coins and NFTs across Binance and multi-chain wallets
                </Typography>
              </Box>
              <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
                <Tooltip title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}>
                  <IconButton
                    aria-label="toggle theme"
                    onClick={() => setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))}
                    size="small"
                    sx={{ border: 1, borderColor: 'divider' }}
                  >
                    {theme === 'dark' ? <LightModeRoundedIcon fontSize="small" /> : <DarkModeRoundedIcon fontSize="small" />}
                  </IconButton>
                </Tooltip>
                {navItems.map((item) => (
                  <Button
                    key={item.key}
                    variant={route === item.key ? 'contained' : 'outlined'}
                    onClick={() => setRoute(item.key)}
                    startIcon={item.icon}
                    sx={{ borderRadius: 3, px: 2 }}
                  >
                    {item.label}
                  </Button>
                ))}
              </Stack>
            </Stack>
          </Paper>

          {route === 'dashboard' ? <Dashboard/> : route === 'assets' ? <Assets/> : route === 'nfts' ? <Nfts/> : <></>}
          {route === 'admin' ? (
            <React.Suspense fallback={<Typography color="text.secondary">Loading Admin...</Typography>}>
              <AdminPage />
            </React.Suspense>
          ) : null}
        </Box>
      </Box>
    </ThemeProvider>
  )
}
