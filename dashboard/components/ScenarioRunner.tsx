'use client';

import { useState } from 'react';
import useSWR from 'swr';
import ProviderSelector from './ProviderSelector';

interface Props {
  onRunStarted: (runId: string) => void;
  onClose: () => void;
}

const ALL_SCENARIOS = [
  { id: 'google_login', label: 'Google Login', budget: '30s', icon: '🔑' },
  { id: 'play_store_install', label: 'Play Store Install', budget: '40s', icon: '📦' },
  { id: 'mlbb_registration', label: 'MLBB Registration', budget: '40s', icon: '🎮' },
  { id: 'google_pay_purchase', label: 'Google Pay Purchase', budget: '30s', icon: '💳' },
];

const fetcher = (url: string) => fetch(url).then((r) => r.json());

export default function ScenarioRunner({ onRunStarted, onClose }: Props) {
  const [selectedProvider, setSelectedProvider] = useState('local');
  const [selectedScenarios, setSelectedScenarios] = useState<string[]>(
    ALL_SCENARIOS.map((s) => s.id)
  );
  const [googleEmail, setGoogleEmail] = useState('');
  const [googlePassword, setGooglePassword] = useState('');
  const [testMode, setTestMode] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: providersData } = useSWR('/api/providers', fetcher);
  const providers = providersData?.providers ?? [];

  const toggleScenario = (id: string) => {
    setSelectedScenarios((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  };

  const handleSubmit = async () => {
    if (selectedScenarios.length === 0) {
      setError('Select at least one scenario');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch('/api/scenarios', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: selectedProvider,
          scenarios: selectedScenarios,
          google_email: googleEmail,
          google_password: googlePassword,
          google_pay_test_mode: testMode,
          total_budget_seconds: 180,
        }),
      });
      if (!resp.ok) {
        const data = await resp.json();
        throw new Error(data.error || 'Failed to start run');
      }
      const data = await resp.json();
      onRunStarted(data.run_id);
    } catch (err: any) {
      setError(err.message || 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const totalBudget = ALL_SCENARIOS.filter((s) => selectedScenarios.includes(s.id))
    .reduce((sum) => sum + 35, 30); // rough estimate

  return (
    <div className="card animate-slide-in">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-semibold text-white text-lg">New Pipeline Run</h2>
        <button onClick={onClose} className="text-gray-400 hover:text-gray-200 transition-colors text-xl leading-none">
          ✕
        </button>
      </div>

      <div className="space-y-6">
        {/* Provider */}
        <div>
          <label className="label mb-3 block">Device Provider</label>
          <ProviderSelector
            providers={providers}
            selected={selectedProvider}
            onChange={setSelectedProvider}
          />
        </div>

        {/* Scenarios */}
        <div>
          <label className="label mb-3 block">Scenarios to Run</label>
          <div className="space-y-2">
            {ALL_SCENARIOS.map((s) => {
              const checked = selectedScenarios.includes(s.id);
              return (
                <label
                  key={s.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    checked
                      ? 'bg-brand-500/10 border-brand-500/40'
                      : 'bg-surface-700 border-surface-600 hover:border-surface-500'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleScenario(s.id)}
                    className="accent-brand-500"
                  />
                  <span className="text-lg">{s.icon}</span>
                  <div className="flex-1">
                    <span className="text-sm font-medium text-gray-200">{s.label}</span>
                  </div>
                  <span className="text-xs text-gray-500 font-mono">{s.budget}</span>
                </label>
              );
            })}
          </div>
        </div>

        {/* Credentials */}
        <div className="space-y-3">
          <label className="label block">Google Account</label>
          <input
            type="email"
            placeholder="test@gmail.com"
            value={googleEmail}
            onChange={(e) => setGoogleEmail(e.target.value)}
            className="input"
          />
          <input
            type="password"
            placeholder="Password"
            value={googlePassword}
            onChange={(e) => setGooglePassword(e.target.value)}
            className="input"
          />
          <p className="text-xs text-gray-500">
            Use a dedicated test account. Credentials are not stored.
          </p>
        </div>

        {/* Test mode */}
        <label className="flex items-center gap-3 cursor-pointer">
          <div
            onClick={() => setTestMode(!testMode)}
            className={`relative w-10 h-5 rounded-full transition-colors ${testMode ? 'bg-brand-600' : 'bg-surface-600'}`}
          >
            <div className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform shadow ${testMode ? 'translate-x-5' : ''}`} />
          </div>
          <div>
            <span className="text-sm text-gray-200">Test payment mode</span>
            <p className="text-xs text-gray-500">Use Google Play test card (no real charge)</p>
          </div>
        </label>

        {/* Budget indicator */}
        <div className="bg-surface-700 rounded-lg p-3">
          <div className="flex justify-between text-xs text-gray-400 mb-1.5">
            <span>Estimated budget</span>
            <span className="font-mono">180s max</span>
          </div>
          <div className="bg-surface-600 rounded-full h-1.5">
            <div
              className="bg-brand-500 h-1.5 rounded-full transition-all"
              style={{ width: `${Math.min(100, (selectedScenarios.length / 4) * 100)}%` }}
            />
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-sm text-red-400">
            {error}
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button onClick={onClose} className="btn-secondary flex-1">
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={loading || selectedScenarios.length === 0}
            className="btn-primary flex-1"
          >
            {loading ? 'Starting...' : '▶ Start Run'}
          </button>
        </div>
      </div>
    </div>
  );
}
