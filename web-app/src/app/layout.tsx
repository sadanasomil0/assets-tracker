import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Price Alert Dashboard',
  description: 'Track crypto, stocks, and commodities with real-time alerts',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
