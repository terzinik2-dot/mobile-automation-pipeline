'use client';

import { useParams } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import { formatDistanceToNow, format } from 'date-fns';
import RunTimeline from '@/components/RunTimeline';
import ArtifactViewer from '@/components/ArtifactViewer';
import LiveStatus from '@/components/LiveStatus';

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function statusBadge(status: string) {
  const map: Record<string, string> = {
    pending: 'badge badge-gray',
    running: 'badge badge-blue',
    completed: 'badge badge-green',
    failed: 'badge badge-red',
    timeout: 'badge badge-yellow',
    cancelled: 'badge badge-gray',
  };
  return map[status] || 'badge badge-gray';
}

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.id as string;

  const { data, isLoading } = useSWR(
    `/api/runs/${runId}`,
    fetcher,
    {
      refreshInterval: (data) =>
        data?.status === 'running' || data?.status === 'pending' ? 2000 : 0,
    }
  );

  const { data: artifacts } = useSWR(`/api/runs/${runId}/artifacts`, fetcher, {
    refreshInterval: data?.status === 'running' ? 3000 : 0,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400">Loading run...</div>
      </div>
    );
  }

  if (!data || data.detail) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <p className="text-gray-400 mb-4">Run not found</p>
          <Link href="/dashboard" className="btn-secondary text-sm">← Back</Link>
        </div>
      </div>
    );
  }

  const timing = data.result?.timing;
  const totalSeconds = timing?.total_ms ? (timing.total_ms / 1000).toFixed(1) : null;
  const isRunning = data.status === 'running' || data.status === 'pending';

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-surface-700 px-6 py-4 flex items-center gap-3 sticky top-0 bg-surface-900 z-10">
        <Link href="/dashboard" className="text-gray-400 hover:text-gray-200 text-sm transition-colors">
          ← Runs
        </Link>
        <span className="text-surface-600">/</span>
        <span className="font-mono text-sm text-gray-400">{runId.slice(0, 8)}...</span>
        <span className={statusBadge(data.status)}>{data.status}</span>
      </nav>

      <div className="flex-1 max-w-6xl mx-auto w-full px-6 py-8 space-y-6">
        {/* Live status */}
        {isRunning && (
          <LiveStatus runId={runId} compact />
        )}

        {/* Summary card */}
        <div className="card">
          <div className="flex items-start justify-between mb-4">
            <div>
              <h1 className="font-semibold text-white text-lg mb-1">
                Run {runId.slice(0, 8)}
              </h1>
              <div className="flex items-center gap-3 text-sm text-gray-400">
                <span>Provider: {data.config?.provider?.provider_type ?? 'unknown'}</span>
                {data.created_at && (
                  <>
                    <span>·</span>
                    <span>
                      {format(new Date(data.created_at), 'MMM d, yyyy HH:mm')}
                    </span>
                  </>
                )}
              </div>
            </div>
            {totalSeconds && (
              <div className="text-right">
                <div className="text-2xl font-bold text-white">{totalSeconds}s</div>
                <div className="text-xs text-gray-400">of 180s budget</div>
              </div>
            )}
          </div>

          {/* Timing breakdown */}
          {timing && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {[
                { label: 'Connect', ms: timing.device_connect_ms },
                { label: 'Google Login', ms: timing.google_login_ms },
                { label: 'Play Store', ms: timing.play_store_install_ms },
                { label: 'MLBB Reg.', ms: timing.mlbb_registration_ms },
                { label: 'Google Pay', ms: timing.google_pay_purchase_ms },
                { label: 'Cleanup', ms: timing.cleanup_ms },
              ].map(({ label, ms }) => (
                <div key={label} className="bg-surface-700 rounded-lg p-3">
                  <div className="label mb-1">{label}</div>
                  <div className="text-sm font-medium text-white">
                    {ms ? `${(ms / 1000).toFixed(1)}s` : '—'}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Error message */}
          {data.error && (
            <div className="mt-4 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
              <p className="text-sm text-red-400 font-medium mb-1">Error</p>
              <p className="text-xs text-red-300 font-mono">{data.error}</p>
            </div>
          )}
        </div>

        {/* Run timeline */}
        {data.result?.scenarios && (
          <div className="card">
            <h2 className="font-semibold text-white mb-4">Step Timeline</h2>
            <RunTimeline scenarios={data.result.scenarios} />
          </div>
        )}

        {/* Artifacts */}
        {artifacts?.artifacts && artifacts.artifacts.length > 0 && (
          <div className="card">
            <h2 className="font-semibold text-white mb-4">
              Artifacts
              <span className="ml-2 text-xs text-gray-400 font-normal">
                ({artifacts.artifacts.length} files)
              </span>
            </h2>
            <ArtifactViewer artifacts={artifacts.artifacts} />
          </div>
        )}

        {/* Locator stats */}
        {data.result?.locator_success_by_layer && (
          <div className="card">
            <h2 className="font-semibold text-white mb-4">Locator Layer Analytics</h2>
            <div className="space-y-2">
              {Object.entries(data.result.locator_success_by_layer)
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .map(([layer, count]) => {
                  const total = Object.values(data.result.locator_success_by_layer).reduce(
                    (s: number, c) => s + (c as number), 0
                  );
                  const pct = total > 0 ? Math.round(((count as number) / total) * 100) : 0;
                  return (
                    <div key={layer} className="flex items-center gap-3">
                      <div className="w-32 text-xs text-gray-400 font-mono">{layer}</div>
                      <div className="flex-1 bg-surface-700 rounded-full h-2">
                        <div
                          className="bg-brand-500 h-2 rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="w-12 text-right text-xs text-gray-400">{count as number}x</div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
