import type { Metadata } from 'next'
import 'bootstrap/dist/css/bootstrap.min.css'
import '../styles/globals.css'

export const metadata: Metadata = {
  title: 'PartSelect Customer Support - AI Assistant',
  description: 'Get help with appliance parts and repairs using our AI-powered assistant',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  )
}