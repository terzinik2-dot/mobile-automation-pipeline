import Link from 'next/link';
import { SignedIn, SignedOut } from '@clerk/nextjs';

export default function HomePage() {
  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-surface-700 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-label="Pipeline logo">
              <rect width="28" height="28" rx="6" fill="#4f46e5"/>
              <rect x="6" y="8" width="4" height="12" rx="1.5" fill="white" opacity="0.9"/>
              <rect x="12" y="5" width="4" height="18" rx="1.5" fill="white"/>
              <rect x="18" y="10" width="4" height="8" rx="1.5" fill="white" opacity="0.7"/>
            </svg>
            <span className="font-semibold text-lg text-white">AutoPipeline</span>
          </div>
          <div className="flex items-center gap-3">
            <SignedOut>
              <Link href="/sign-in" className="btn-secondary text-sm">Sign In</Link>
              <Link href="/sign-up" className="btn-primary text-sm">Get Started</Link>
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard" className="btn-primary text-sm">Dashboard →</Link>
            </SignedIn>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 max-w-6xl mx-auto px-6 pt-24 pb-16">
        <div className="text-center max-w-3xl mx-auto mb-20">
          <div className="inline-flex items-center gap-2 bg-brand-500/10 border border-brand-500/30 rounded-full px-4 py-1.5 text-sm text-brand-500 mb-6">
            <span className="w-2 h-2 rounded-full bg-brand-500 inline-block"></span>
            Google Login → Play Store → MLBB → Google Pay
          </div>
          <h1 className="text-5xl font-bold tracking-tight text-white mb-6 leading-tight">
            Mobile automation<br />
            <span className="text-brand-500">in under 3 minutes</span>
          </h1>
          <p className="text-lg text-gray-400 mb-8 max-w-xl mx-auto">
            Automate complex Android workflows across real device farms using
            a self-healing CV/OCR locator cascade. Never break on UI changes.
          </p>
          <div className="flex items-center justify-center gap-4">
            <SignedOut>
              <Link href="/sign-up" className="btn-primary px-6 py-3 text-base">
                Start automating →
              </Link>
            </SignedOut>
            <SignedIn>
              <Link href="/dashboard" className="btn-primary px-6 py-3 text-base">
                Open dashboard →
              </Link>
            </SignedIn>
            <a href="https://github.com" className="btn-secondary px-6 py-3 text-base" target="_blank">
              View source
            </a>
          </div>
        </div>

        {/* Feature grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {features.map((f) => (
            <div key={f.title} className="card">
              <div className="text-2xl mb-3">{f.icon}</div>
              <h3 className="font-semibold text-white mb-1.5">{f.title}</h3>
              <p className="text-sm text-gray-400 leading-relaxed">{f.description}</p>
            </div>
          ))}
        </div>

        {/* Tech stack */}
        <div className="mt-20 text-center">
          <p className="label mb-6">Tech stack</p>
          <div className="flex flex-wrap justify-center gap-3">
            {stack.map((t) => (
              <span key={t} className="bg-surface-700 border border-surface-600 text-gray-300 px-4 py-1.5 rounded-full text-sm">
                {t}
              </span>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-700 px-6 py-6 text-center">
        <p className="text-sm text-gray-500">
          Mobile Automation Pipeline — Built for the COO interview assignment
        </p>
      </footer>
    </div>
  );
}

const features = [
  {
    icon: '🔍',
    title: 'Self-Healing Locators',
    description: '7-layer cascade: resource-id → text → content-desc → accessibility → XPath → OpenCV → Tesseract OCR. Survives UI changes automatically.',
  },
  {
    icon: '☁️',
    title: 'Multi-Provider',
    description: 'Runs on BrowserStack, AWS Device Farm, or your own Android device via ADB. Swap providers with one env var.',
  },
  {
    icon: '⏱️',
    title: 'Sub-3-Minute Pipeline',
    description: 'Budget-aware orchestration: each step has a hard time limit. Total budget: 180 seconds. Overruns steal from reserve.',
  },
  {
    icon: '📸',
    title: 'Rich Artifacts',
    description: 'Auto-screenshots on step failure, full session video, logcat logs, and locator analytics per run.',
  },
  {
    icon: '🔄',
    title: 'Retry Logic',
    description: 'Each step retries up to 3 times with exponential backoff. Critical failures abort; optional scenarios gracefully degrade.',
  },
  {
    icon: '📊',
    title: 'Live Dashboard',
    description: 'Real-time WebSocket updates, step timeline visualization, screenshot viewer, and provider performance analytics.',
  },
];

const stack = [
  'Python 3.11',
  'Appium 2.0',
  'OpenCV',
  'Tesseract OCR',
  'FastAPI',
  'SQLite',
  'Next.js 14',
  'Clerk Auth',
  'Tailwind CSS',
  'BrowserStack',
  'AWS Device Farm',
];
