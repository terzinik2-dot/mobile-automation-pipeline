import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'Mobile Automation Pipeline',
  description: 'Automate mobile app testing on real device farms',
};

// Conditionally wrap with ClerkProvider only if keys exist
async function MaybeClerkProvider({ children }: { children: React.ReactNode }) {
  const publishableKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY;
  if (publishableKey) {
    const { ClerkProvider } = await import('@clerk/nextjs');
    return <ClerkProvider>{children}</ClerkProvider>;
  }
  return <>{children}</>;
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <MaybeClerkProvider>
      <html lang="en" className={inter.variable}>
        <body className="bg-surface-900 text-gray-100 antialiased">
          {children}
        </body>
      </html>
    </MaybeClerkProvider>
  );
}
