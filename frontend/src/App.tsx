import React from 'react'
import AccountBalanceWalletRoundedIcon from '@mui/icons-material/AccountBalanceWalletRounded'
import AdminPanelSettingsRoundedIcon from '@mui/icons-material/AdminPanelSettingsRounded'
import SettingsSuggestRoundedIcon from '@mui/icons-material/SettingsSuggestRounded'
import CollectionsRoundedIcon from '@mui/icons-material/CollectionsRounded'
import DarkModeRoundedIcon from '@mui/icons-material/DarkModeRounded'
import DashboardRoundedIcon from '@mui/icons-material/DashboardRounded'
import KeyboardDoubleArrowLeftRoundedIcon from '@mui/icons-material/KeyboardDoubleArrowLeftRounded'
import KeyboardDoubleArrowRightRoundedIcon from '@mui/icons-material/KeyboardDoubleArrowRightRounded'
import LightModeRoundedIcon from '@mui/icons-material/LightModeRounded'
import PaidRoundedIcon from '@mui/icons-material/PaidRounded'
import { Box, Button, CssBaseline, IconButton, Paper, Stack, ThemeProvider, Tooltip, Typography } from '@mui/material'
import Assets from './pages/Assets'
import Dashboard from './pages/Dashboard'
import Nfts from './pages/Nfts'
import { updateCurrencySetting } from './shared/api'
import { buildTheme, type AppMode } from './theme'
import changelog from '../../CHANGELOG.md?raw'

const AccountsPage = React.lazy(() => import('./pages/Admin'))
const AutomationPage = React.lazy(() => import('./pages/Automation'))
type Theme = AppMode
type CurrencyMode = 'EUR' | 'USD'
const APP_VERSION = changelog.match(/^## \[(\d{4}\.\d{2}\.\d{2})\]/m)?.[1] ?? 'unknown'

export default function App(){
  const [route, setRoute] = React.useState<'dashboard'|'assets'|'nfts'|'accounts'|'automation'>('dashboard')
  const [theme, setTheme] = React.useState<Theme>(() => {
    const saved = window.localStorage.getItem('cpt_theme')
    if (saved === 'dark' || saved === 'light') return saved
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  })
  const [currencyMode, setCurrencyMode] = React.useState<CurrencyMode>(() => {
    const saved = window.localStorage.getItem('cpt_currency_mode')
    if (saved === 'EUR' || saved === 'USD') return saved
    return 'USD'
  })
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState<boolean>(() => {
    const saved = window.localStorage.getItem('cpt_sidebar_collapsed')
    return saved === '1'
  })
  const navItems: Array<{ key: 'dashboard' | 'assets' | 'nfts' | 'accounts' | 'automation'; label: string; icon: React.ReactNode }> = [
    { key: 'dashboard', label: 'Dashboard', icon: <DashboardRoundedIcon fontSize="small" /> },
    { key: 'assets', label: 'Coins', icon: <PaidRoundedIcon fontSize="small" /> },
    { key: 'nfts', label: 'NFTs', icon: <CollectionsRoundedIcon fontSize="small" /> },
    { key: 'accounts', label: 'Accounts', icon: <AdminPanelSettingsRoundedIcon fontSize="small" /> },
    { key: 'automation', label: 'Sync & Notifications', icon: <SettingsSuggestRoundedIcon fontSize="small" /> },
  ]
  const themeObj = React.useMemo(() => buildTheme(theme), [theme])
  const activeNav = navItems.find((item) => item.key === route)

  React.useEffect(() => {
    window.localStorage.setItem('cpt_theme', theme)
  }, [theme])
  React.useEffect(() => {
    window.localStorage.setItem('cpt_currency_mode', currencyMode)
    updateCurrencySetting(currencyMode).catch(() => {})
  }, [currencyMode])
  React.useEffect(() => {
    window.localStorage.setItem('cpt_sidebar_collapsed', isSidebarCollapsed ? '1' : '0')
  }, [isSidebarCollapsed])

  const renderCurrencyToggle = () => {
    return (
      <Box
        sx={{
          position: 'relative',
          display: 'inline-flex',
          p: 0.4,
          borderRadius: 999,
          border: 1,
          borderColor: 'divider',
          bgcolor: 'action.hover',
          minWidth: 132,
        }}
      >
        <Box
          sx={{
            position: 'absolute',
            top: 3,
            bottom: 3,
            left: currencyMode === 'USD' ? 3 : 'calc(50% + 1px)',
            width: 'calc(50% - 4px)',
            borderRadius: 999,
            bgcolor: 'primary.main',
            transition: 'left .18s ease',
          }}
        />
        {(['USD', 'EUR'] as CurrencyMode[]).map((curr) => (
          <Button
            key={curr}
            size="small"
            variant="text"
            onClick={() => setCurrencyMode(curr)}
            sx={{
              zIndex: 1,
              flex: 1,
              minWidth: 0,
              color: currencyMode === curr ? 'primary.contrastText' : 'text.secondary',
              fontWeight: currencyMode === curr ? 700 : 500,
              borderRadius: 999,
              '&:hover': { backgroundColor: 'transparent' },
            }}
          >
            {curr}
          </Button>
        ))}
      </Box>
    )
  }

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
          <Stack spacing={2}>
            <Paper
              variant="outlined"
              sx={{
                p: 2.5,
                borderRadius: '16px',
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
                    {activeNav?.label || 'Dashboard'}
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
                  {renderCurrencyToggle()}
                </Stack>
              </Stack>
            </Paper>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="flex-start">
              <Paper
                variant="outlined"
                sx={{
                  width: { xs: '100%', md: isSidebarCollapsed ? 92 : 250 },
                  p: 2,
                  borderRadius: '16px',
                  backdropFilter: 'blur(8px)',
                  background: (t) =>
                    t.palette.mode === 'dark'
                      ? 'linear-gradient(170deg, rgba(17,24,45,0.88), rgba(13,19,37,0.92))'
                      : 'linear-gradient(170deg, rgba(255,255,255,0.92), rgba(248,251,255,0.94))',
                  display: 'flex',
                  flexDirection: 'column',
                }}
              >
                <Stack
                  direction={{ xs: 'row', md: 'column' }}
                  spacing={1}
                  useFlexGap
                  sx={{
                    overflowX: { xs: 'auto', md: 'visible' },
                    pb: { xs: 0.5, md: 0 },
                    alignItems: { md: isSidebarCollapsed ? 'center' : 'stretch' },
                    flex: 1,
                  }}
                >
                  <Tooltip title={isSidebarCollapsed ? 'Expand menu' : 'Collapse menu'}>
                    <IconButton
                      aria-label={isSidebarCollapsed ? 'expand sidebar' : 'collapse sidebar'}
                      onClick={() => setIsSidebarCollapsed((prev) => !prev)}
                      size="small"
                      sx={{
                        display: { xs: 'none', md: 'inline-flex' },
                        alignSelf: isSidebarCollapsed ? 'center' : 'flex-end',
                        mb: 0.5,
                        color: 'text.secondary',
                        opacity: 0.68,
                        width: 28,
                        height: 28,
                        '&:hover': {
                          opacity: 1,
                          color: 'text.primary',
                          bgcolor: 'action.hover',
                        },
                      }}
                    >
                      {isSidebarCollapsed ? <KeyboardDoubleArrowRightRoundedIcon fontSize="small" /> : <KeyboardDoubleArrowLeftRoundedIcon fontSize="small" />}
                    </IconButton>
                  </Tooltip>
                  {navItems.map((item) => (
                    <Tooltip
                      key={item.key}
                      title={item.label}
                      placement="right"
                      disableHoverListener={!isSidebarCollapsed}
                    >
                      <Button
                        variant={route === item.key ? 'contained' : 'text'}
                        onClick={() => setRoute(item.key)}
                        startIcon={item.icon}
                        sx={{
                          borderRadius: 3,
                          justifyContent: { xs: 'flex-start', md: isSidebarCollapsed ? 'center' : 'flex-start' },
                          px: { xs: 1.4, md: isSidebarCollapsed ? 1 : 1.4 },
                          py: 1,
                          minWidth: { xs: 120, md: '100%' },
                          width: { md: isSidebarCollapsed ? 48 : '100%' },
                          whiteSpace: 'nowrap',
                          '& .MuiButton-startIcon': {
                            mr: { xs: 1, md: isSidebarCollapsed ? 0 : 1 },
                          },
                        }}
                      >
                        <Box component="span" sx={{ display: { xs: 'inline', md: isSidebarCollapsed ? 'none' : 'inline' } }}>
                          {item.label}
                        </Box>
                      </Button>
                    </Tooltip>
                  ))}
                </Stack>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{
                    mt: 1,
                    px: 0.5,
                    alignSelf: 'flex-start',
                    opacity: 0.75,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {isSidebarCollapsed ? `v${APP_VERSION}` : `Version ${APP_VERSION}`}
                </Typography>
              </Paper>

              <Box sx={{ flex: 1, minWidth: 0 }}>
                {route === 'dashboard' ? <Dashboard currencyMode={currencyMode} /> : route === 'assets' ? <Assets/> : route === 'nfts' ? <Nfts/> : <></>}
                {route === 'accounts' ? (
                  <React.Suspense fallback={<Typography color="text.secondary">Loading Accounts...</Typography>}>
                    <AccountsPage />
                  </React.Suspense>
                ) : null}
                {route === 'automation' ? (
                  <React.Suspense fallback={<Typography color="text.secondary">Loading Sync & Notifications...</Typography>}>
                    <AutomationPage />
                  </React.Suspense>
                ) : null}
              </Box>
            </Stack>
          </Stack>
        </Box>
      </Box>
    </ThemeProvider>
  )
}
