import { createTheme } from '@mui/material/styles'

export type AppMode = 'light' | 'dark'

export function buildTheme(mode: AppMode) {
  const isDark = mode === 'dark'
  return createTheme({
    palette: {
      mode,
      primary: { main: '#5b8def' },
      secondary: { main: '#ff9800' },
      background: {
        default: isDark ? '#0b1020' : '#f3f6fc',
        paper: isDark ? '#11182d' : '#ffffff',
      },
    },
    shape: { borderRadius: 16 },
    typography: {
      fontFamily: '"Manrope", "Space Grotesk", "Segoe UI", sans-serif',
      h4: { fontWeight: 700 },
      h5: { fontWeight: 700 },
      h6: { fontWeight: 700 },
    },
    components: {
      MuiPaper: {
        styleOverrides: {
          root: {
            borderRadius: 16,
            borderColor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(13,26,47,0.12)',
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            borderRadius: 16,
            borderColor: isDark ? 'rgba(255,255,255,0.12)' : 'rgba(13,26,47,0.12)',
            boxShadow: isDark ? '0 14px 34px rgba(0,0,0,0.28)' : '0 10px 30px rgba(13, 32, 63, 0.08)',
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: { borderRadius: 12, textTransform: 'none', fontWeight: 600 },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: { borderRadius: 12 },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: { borderBottom: '1px solid rgba(128,128,128,0.18)' },
          head: { fontWeight: 700 },
        },
      },
    },
  })
}
