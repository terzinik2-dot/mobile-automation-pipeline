'use client';

interface Provider {
  provider_id: string;
  name: string;
  description: string;
  configured: boolean;
  required_env_vars: string[];
}

interface Props {
  providers: Provider[];
  selected: string;
  onChange: (id: string) => void;
}

const providerIcons: Record<string, string> = {
  local: '💻',
  browserstack: '☁️',
  aws_device_farm: '🏗️',
};

export default function ProviderSelector({ providers, selected, onChange }: Props) {
  if (!providers || providers.length === 0) {
    return (
      <div className="text-sm text-gray-400 py-2">
        Loading providers...
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
      {providers.map((p) => {
        const isSelected = selected === p.provider_id;
        const isDisabled = !p.configured;

        return (
          <button
            key={p.provider_id}
            onClick={() => !isDisabled && onChange(p.provider_id)}
            disabled={isDisabled}
            className={`relative p-3 rounded-lg border text-left transition-all ${
              isSelected
                ? 'bg-brand-500/15 border-brand-500/50 ring-1 ring-brand-500/30'
                : isDisabled
                ? 'bg-surface-800 border-surface-600 opacity-50 cursor-not-allowed'
                : 'bg-surface-700 border-surface-600 hover:border-surface-500 cursor-pointer'
            }`}
          >
            <div className="flex items-start gap-2">
              <span className="text-xl">{providerIcons[p.provider_id] || '📱'}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-gray-200 truncate">{p.name}</span>
                  {p.configured ? (
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 flex-shrink-0" title="Configured" />
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-gray-600 flex-shrink-0" title="Not configured" />
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{p.description}</p>
              </div>
            </div>

            {!p.configured && p.required_env_vars.length > 0 && (
              <div className="mt-2 text-xs text-gray-500">
                Requires: {p.required_env_vars.slice(0, 2).join(', ')}
                {p.required_env_vars.length > 2 && ` +${p.required_env_vars.length - 2} more`}
              </div>
            )}

            {isSelected && (
              <div className="absolute top-2 right-2 w-4 h-4 rounded-full bg-brand-500 flex items-center justify-center">
                <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                  <path d="M1 3.5L3.5 6L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}
