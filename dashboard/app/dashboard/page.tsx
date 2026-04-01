'use client';

import { useState } from 'react';
import { UserButton } from '@clerk/nextjs';
import Link from 'next/link';
import useSWR from 'swr';
import { formatDistanceToNow } from 'date-fns';
import ScenarioRunner from '@/components/ScenarioRunner';
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

export default function DashboardPage() {
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [showRunner, setShowRunner] = useState(false);

  const { data, mutate } = useSWR('/api/runs', fetcher, { refreshInterval: 5000 });

  const runs = data?.runs ?? [];

  const handleRunStarted = (runId: string) => {
    setActiveRunId(runId);
    setShowRunner(false);
    mutate();
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Top nav */}
      <nav className="border-b border-surface-700 px-6 py-4 flex items-center justify-between sticky top-0 bg-surface-900 z-10">
        <div className="flex items-center gap-3">
          <Link href="/" className="flex items-center gap-2">
            <svg width="24" height="24" viewBox="0 0 28 28" fill="none">
              <rect width="28" height="28" rx="6" fill="#4f46e5"/>
              <rect x="6" y="8" width="4" height="12" rx="1.5" fill="white" opacity="0.9"/>
              <rect x="12" y="5" width="4" height="18" rx="1.5" fill="white"/>
              <rect x="18" y="10" width="4" height="8" rx="1.5" fill="white" opacity="0.7"/>
            </svg>
            <span className="font-semibold text-white">AutoPipeline</span>
          </Link>
          <span className="text-surface-600">/</span>
          <span className="text-gray-400 text-sm">Dashboard</span>
        </div>
        <UserButton afterSignOutUrl="/" />
      </nav>

      <div className="flex-1 max-w-6xl mx-auto w-full px-6 py-8">
        {/* Header row */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-white">Pipeline Runs</h1>
            <p className="text-gray-400 text-sm mt-1">
              {data?.total ?? 0} total runs
            </p>
          </div>
          <button
            onClick={() => setShowRunner(true)}
            className="btn-primary"
          >
            + New Run
          </button>
        </div>

        {/* Live status for active run */}
        {activeRunId && (
          <div className="mb-6">
            <LiveStatus runId={activeRunId} />
          </div>
        )}

        {/* Scenario runner modal */}
        {showRunner && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="w-full max-w-2xl">
              <ScenarioRunner
                onRunStarted={handleRunStarted}
                onClose={() => setShowRunner(false)}
              />
            </div>
          </div>
        )}

        {/* Runs table */}
        <div className="card p-0 overflow-hidden">
          <div className="border-b border-surface-600 px-5 py-3 flex items-center gap-4">
            <h2 className="font-medium text-white text-sm">Recent Runs</h2>
            <button
              onClick={() => mutate()}
              className="ml-auto text-gray-400 hover:text-gray-200 text-sm transition-colors"
            >
              Refresh
            </button>
          </div>
          {runs.length === 0 ? (
            <div className="px-5 py-16 text-center">
              <div className="text-4xl mb-3">🤖</div>
              <p className="text-gray-400 text-sm">No runs yet — start your first pipeline run</p>
              <button
                onClick={() => setShowRunner(true)}
                className="btn-primary mt-4 text-sm"
              >
                Start New Run
              </button>
            </div>
          ) : (
            <div className="divide-y divide-surface-700">
              {runs.map((run: any) => (
                <Link
                  key={run.run_id}
                  href={`/dashboard/runs/${run.run_id}`}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-surface-700/50 transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs text-gray-500 truncate">
                        {run.run_id.slice(0, 8)}...
                      </span>
                      <span className={statusBadge(run.status)}>{run.status}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-400">
                      <span>{run.provider}</span>
                      <span>·</span>
                      <span>{(run.scenarios || []).length} scenarios</span>
                      {run.timing_total_ms && (
                        <>
                          <span>·</span>
                          <span>{(run.timing_total_ms / 1000).toFixed(1)}s</span>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 whitespace-nowrap">
                    {run.created_at
                      ? formatDistanceToNow(new Date(run.created_at), { addSuffix: true })
                      : 'unknown'}
                  </div>
                  <div className="text-gray-600">→</div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
