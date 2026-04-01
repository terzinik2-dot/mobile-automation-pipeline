'use client';

import { useEffect, useState, useRef } from 'react';

interface StatusEvent {
  event: string;
  run_id?: string;
  status?: string;
  step?: string;
  scenario?: string;
  timestamp?: string;
  timing_total_ms?: number;
  success_rate?: number;
  error?: string;
}

interface Props {
  runId: string;
  compact?: boolean;
}

const scenarioLabels: Record<string, string> = {
  google_login: 'Google Login',
  play_store_install: 'Play Store Install',
  mlbb_registration: 'MLBB Registration',
  google_pay_purchase: 'Google Pay Purchase',
};

export default function LiveStatus({ runId, compact = false }: Props) {
  const [status, setStatus] = useState<string>('connecting');
  const [events, setEvents] = useState<StatusEvent[]>([]);
  const [currentScenario, setCurrentScenario] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [startTime] = useState(() => Date.now());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Elapsed timer
  useEffect(() => {
    if (status === 'running' || status === 'connecting' || status === 'pending') {
      const interval = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [status, startTime]);

  // WebSocket connection
  useEffect(() => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const wsUrl = apiUrl.replace(/^http/, 'ws') + `/ws/runs/${runId}`;

    const connect = () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
      };

      ws.onmessage = (e) => {
        try {
          const data: StatusEvent = JSON.parse(e.data);
          if (data.event === 'initial_state') {
            setStatus(data.status || 'unknown');
          } else if (data.event === 'status_change') {
            setStatus(data.status || 'unknown');
          } else if (data.event === 'step_update') {
            setCurrentScenario(data.scenario || null);
            setEvents((prev) => [data, ...prev].slice(0, 20));
          } else if (data.event === 'run_complete' || data.event === 'run_failed') {
            setStatus(data.status || (data.event === 'run_failed' ? 'failed' : 'completed'));
            setEvents((prev) => [data, ...prev].slice(0, 20));
          }
        } catch {}
      };

      ws.onclose = () => {
        // Only reconnect if run is still active
        if (status !== 'completed' && status !== 'failed' && status !== 'timeout') {
          reconnectRef.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };
    };

    connect();

    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [runId]);

  const budgetPct = Math.min(100, (elapsed / 180) * 100);
  const budgetColor = budgetPct > 90 ? 'bg-red-500' : budgetPct > 70 ? 'bg-amber-500' : 'bg-brand-500';

  if (compact) {
    return (
      <div className="flex items-center gap-4 bg-surface-800 border border-surface-600 rounded-lg px-4 py-3">
        <div className="flex items-center gap-2">
          {status === 'running' && (
            <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse-slow" />
          )}
          <span className="text-sm text-gray-300 font-medium capitalize">{status}</span>
        </div>
        {currentScenario && (
          <span className="text-xs text-gray-400">
            {scenarioLabels[currentScenario] || currentScenario}
          </span>
        )}
        <div className="flex-1 flex items-center gap-2 ml-auto max-w-xs">
          <div className="flex-1 bg-surface-600 rounded-full h-1.5">
            <div className={`${budgetColor} h-1.5 rounded-full transition-all`} style={{ width: `${budgetPct}%` }} />
          </div>
          <span className="text-xs text-gray-400 font-mono w-10 text-right">{elapsed}s</span>
        </div>
      </div>
    );
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {status === 'running' && (
            <span className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-pulse-slow" />
          )}
          <h3 className="font-semibold text-white text-sm">Live Status</h3>
          <span className="text-xs text-gray-400 capitalize">{status}</span>
        </div>
        <div className="font-mono text-sm text-gray-300">{elapsed}s / 180s</div>
      </div>

      {/* Budget bar */}
      <div>
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Time budget</span>
          <span>{Math.max(0, 180 - elapsed)}s remaining</span>
        </div>
        <div className="bg-surface-700 rounded-full h-2">
          <div
            className={`${budgetColor} h-2 rounded-full transition-all`}
            style={{ width: `${budgetPct}%` }}
          />
        </div>
      </div>

      {/* Current scenario */}
      {currentScenario && (
        <div className="flex items-center gap-2 bg-blue-500/10 border border-blue-500/30 rounded-lg px-3 py-2">
          <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
          <span className="text-xs text-blue-300">
            Running: {scenarioLabels[currentScenario] || currentScenario}
          </span>
        </div>
      )}

      {/* Recent events */}
      {events.length > 0 && (
        <div className="space-y-1 max-h-32 overflow-y-auto">
          {events.slice(0, 8).map((e, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-gray-400">
              <span className="text-gray-600 font-mono text-[10px] mt-0.5 flex-shrink-0">
                {e.timestamp ? new Date(e.timestamp).toLocaleTimeString() : ''}
              </span>
              <span className="line-clamp-1">
                {e.event === 'step_update' && `Step: ${e.step || 'unknown'}`}
                {e.event === 'run_complete' && (
                  <span className="text-emerald-400">
                    ✓ Complete — {e.timing_total_ms ? `${(e.timing_total_ms / 1000).toFixed(1)}s` : ''} — {Math.round((e.success_rate || 0) * 100)}% success
                  </span>
                )}
                {e.event === 'run_failed' && (
                  <span className="text-red-400">✗ Failed: {e.error}</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
