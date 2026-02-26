type CurrencyCode = 'EUR' | 'USD'

type CurrencyFormatOptions = {
  minimumFractionDigits?: number
  maximumFractionDigits?: number
  withCode?: boolean
}

const CURRENCY_LOCALE: Record<CurrencyCode, string> = {
  EUR: 'pt-PT',
  USD: 'en-US',
}

export function formatCurrency(value: number, currency: CurrencyCode, options: CurrencyFormatOptions = {}): string {
  const {
    minimumFractionDigits = 2,
    maximumFractionDigits = 2,
    withCode = true,
  } = options
  const locale = CURRENCY_LOCALE[currency]
  const formatted = new Intl.NumberFormat(locale, {
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value)
  return withCode ? `${currency} ${formatted}` : formatted
}

export function formatEur(value: number, options: CurrencyFormatOptions = {}): string {
  return formatCurrency(value, 'EUR', options)
}

export function formatUsd(value: number, options: CurrencyFormatOptions = {}): string {
  return formatCurrency(value, 'USD', options)
}
