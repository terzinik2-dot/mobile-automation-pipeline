'use client';

interface StepResult {
  step_id: string;
  step_name: string;
  scenario_name: string;
  status: string;
  duration_ms: number | null;
  attempt_number: number;
  error_message: string | null;
  locator_attempts: any[];
  artifacts: any[];
}

interface ScenarioResult {
  scenario_id: string;
  scenario_name: string;
  status: string;
  duration_ms: number | null;
  steps: StepResult[];
  error_message: string | null;
}

interface Props {
  scenarios: ScenarioResult[];
}

function stepIcon(status: string) {
  switch (status) {
    case 'completed': return '✓';
    case 'failed': return '✗';
    case 'timeout': return '⏱';
    case 'skipped': return '—';
    case 'running': return '…';
    default: return '○';
  }
}

function stepColor(status: string) {
  switch (status) {
    case 'completed': return 'text-emerald-400 bg-emerald-500/20 border-emerald-500/40';
    case 'failed': return 'text-red-400 bg-red-500/20 border-red-500/40';
    case 'timeout': return 'text-amber-400 bg-amber-500/20 border-amber-500/40';
    case 'skipped': return 'text-gray-500 bg-gray-500/10 border-gray-500/30';
    case 'running': return 'text-blue-400 bg-blue-500/20 border-blue-500/40 animate-pulse-slow';
    default: return 'text-gray-400 bg-surface-700 border-surface-600';
  }
}

function scenarioBadgeColor(status: string) {
  switch (status) {
    case 'completed': return 'badge badge-green';
    case 'failed': return 'badge badge-red';
    case 'timeout': return 'badge badge-yellow';
    case 'skipped': return 'badge badge-gray';
    case 'running': return 'badge badge-blue';
    default: return 'badge badge-gray';
  }
}

export default function RunTimeline({ scenarios }: Props) {
  if (!scenarios || scenarios.length === 0) {
    return <p className="text-sm text-gray-500">No scenario data available.</p>;
  }

  return (
    <div className="space-y-6">
      {scenarios.map((scenario, idx) => (
        <div key={scenario.scenario_id} className="relative">
          {/* Scenario header */}
          <div className="flex items-center gap-3 mb-3">
            <div className="w-6 h-6 rounded-full bg-surface-600 border border-surface-500 flex items-center justify-center text-xs text-gray-400 font-mono font-bold flex-shrink-0">
              {idx + 1}
            </div>
            <h3 className="font-medium text-white text-sm capitalize">
              {scenario.scenario_name.replace(/_/g, ' ')}
            </h3>
            <span className={scenarioBadgeColor(scenario.status)}>{scenario.status}</span>
            {scenario.duration_ms && (
              <span className="text-xs text-gray-500 ml-auto font-mono">
                {(scenario.duration_ms / 1000).toFixed(1)}s
              </span>
            )}
          </div>

          {/* Steps */}
          {scenario.steps && scenario.steps.length > 0 && (
            <div className="ml-9 space-y-1.5">
              {scenario.steps.map((step) => (
                <div key={step.step_id} className="group">
                  <div className="flex items-center gap-2.5">
                    {/* Status icon */}
                    <div className={`w-5 h-5 rounded border text-xs flex items-center justify-center flex-shrink-0 font-mono ${stepColor(step.status)}`}>
                      {stepIcon(step.status)}
                    </div>

                    {/* Step name */}
                    <span className="text-xs text-gray-300 flex-1 capitalize">
                      {step.step_name.replace(/_/g, ' ')}
                      {step.attempt_number > 1 && (
                        <span className="text-amber-400 ml-1.5">(attempt {step.attempt_number})</span>
                      )}
                    </span>

                    {/* Duration */}
                    {step.duration_ms && (
                      <span className="text-xs text-gray-500 font-mono">
                        {step.duration_ms > 1000
                          ? `${(step.duration_ms / 1000).toFixed(1)}s`
                          : `${Math.round(step.duration_ms)}ms`}
                      </span>
                    )}

                    {/* Locator layer badge */}
                    {step.locator_attempts && step.locator_attempts.length > 0 && (() => {
                      const successful = step.locator_attempts.find((a) => a.succeeded);
                      return successful ? (
                        <span className="badge badge-purple text-xs opacity-0 group-hover:opacity-100 transition-opacity">
                          {successful.layer}
                        </span>
                      ) : null;
                    })()}
                  </div>

                  {/* Error message */}
                  {step.error_message && (
                    <div className="ml-7 mt-1 text-xs text-red-400 font-mono bg-red-500/10 rounded px-2 py-1 border border-red-500/20">
                      {step.error_message.slice(0, 200)}
                      {step.error_message.length > 200 && '...'}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Scenario error */}
          {scenario.error_message && scenario.steps?.length === 0 && (
            <div className="ml-9 text-xs text-red-400 font-mono bg-red-500/10 rounded px-2 py-1 border border-red-500/20">
              {scenario.error_message}
            </div>
          )}

          {/* Connector line to next scenario */}
          {idx < scenarios.length - 1 && (
            <div className="absolute left-3 top-9 bottom-0 w-px bg-surface-600" style={{ top: '28px' }} />
          )}
        </div>
      ))}
    </div>
  );
}
