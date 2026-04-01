import { SignIn } from '@clerk/nextjs';

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-900">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-3">
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-label="Logo">
              <rect width="28" height="28" rx="6" fill="#4f46e5"/>
              <rect x="6" y="8" width="4" height="12" rx="1.5" fill="white" opacity="0.9"/>
              <rect x="12" y="5" width="4" height="18" rx="1.5" fill="white"/>
              <rect x="18" y="10" width="4" height="8" rx="1.5" fill="white" opacity="0.7"/>
            </svg>
            <span className="font-semibold text-lg text-white">AutoPipeline</span>
          </div>
          <p className="text-gray-400 text-sm">Sign in to access your dashboard</p>
        </div>
        <SignIn
          appearance={{
            elements: {
              rootBox: 'w-full',
              card: 'bg-surface-800 border border-surface-600 shadow-xl rounded-xl',
              headerTitle: 'text-white',
              headerSubtitle: 'text-gray-400',
              socialButtonsBlockButton: 'bg-surface-700 border-surface-600 text-gray-200 hover:bg-surface-600',
              formFieldLabel: 'text-gray-300',
              formFieldInput: 'bg-surface-700 border-surface-600 text-gray-100 focus:ring-brand-500',
              formButtonPrimary: 'bg-brand-600 hover:bg-brand-700',
              footerActionText: 'text-gray-400',
              footerActionLink: 'text-brand-500',
              dividerLine: 'bg-surface-600',
              dividerText: 'text-gray-500',
            },
          }}
        />
      </div>
    </div>
  );
}
