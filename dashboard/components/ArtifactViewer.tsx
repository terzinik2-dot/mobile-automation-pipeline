'use client';

import { useState } from 'react';

interface Artifact {
  artifact_type: string;
  file_path: string;
  description: string;
  captured_at?: string;
  exists: boolean;
  download_url?: string;
}

interface Props {
  artifacts: Artifact[];
}

const typeIcons: Record<string, string> = {
  screenshot: '📸',
  video: '🎬',
  log_snippet: '📋',
  video_clip: '🎥',
};

export default function ArtifactViewer({ artifacts }: Props) {
  const [selectedIndex, setSelected] = useState<number | null>(null);

  const screenshots = artifacts.filter((a) => a.artifact_type === 'screenshot' && a.exists);
  const videos = artifacts.filter((a) => ['video', 'video_clip'].includes(a.artifact_type) && a.exists);
  const logs = artifacts.filter((a) => a.artifact_type === 'log_snippet' && a.exists);
  const other = artifacts.filter((a) => !['screenshot', 'video', 'video_clip', 'log_snippet'].includes(a.artifact_type));

  const selectedArtifact = selectedIndex !== null ? screenshots[selectedIndex] : null;

  return (
    <div className="space-y-4">
      {/* Screenshots */}
      {screenshots.length > 0 && (
        <div>
          <p className="label mb-2">Screenshots ({screenshots.length})</p>
          <div className="grid grid-cols-3 md:grid-cols-5 lg:grid-cols-7 gap-2">
            {screenshots.map((a, i) => (
              <button
                key={i}
                onClick={() => setSelected(i === selectedIndex ? null : i)}
                className={`relative aspect-[9/16] rounded-lg overflow-hidden border-2 transition-all ${
                  selectedIndex === i ? 'border-brand-500' : 'border-surface-600 hover:border-surface-400'
                } bg-surface-700`}
                title={a.description}
              >
                {a.download_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={a.download_url}
                    alt={a.description}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      (e.target as HTMLImageElement).style.display = 'none';
                    }}
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-2xl">📸</div>
                )}
                <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-1">
                  <p className="text-[9px] text-white truncate leading-tight">{a.description}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Expanded screenshot */}
      {selectedArtifact && (
        <div className="relative">
          <div className="bg-surface-700 rounded-lg p-3 flex items-start gap-4">
            <div className="flex-shrink-0 w-48">
              {selectedArtifact.download_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={selectedArtifact.download_url}
                  alt={selectedArtifact.description}
                  className="rounded border border-surface-600 w-full"
                />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-medium text-sm text-white mb-1">{selectedArtifact.description}</p>
              <p className="text-xs text-gray-400 font-mono truncate">{selectedArtifact.file_path}</p>
              {selectedArtifact.captured_at && (
                <p className="text-xs text-gray-500 mt-1">
                  {new Date(selectedArtifact.captured_at).toLocaleString()}
                </p>
              )}
              {selectedArtifact.download_url && (
                <a
                  href={selectedArtifact.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-block btn-secondary text-xs py-1.5 px-3"
                >
                  Download
                </a>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Videos */}
      {videos.length > 0 && (
        <div>
          <p className="label mb-2">Videos ({videos.length})</p>
          <div className="space-y-2">
            {videos.map((a, i) => (
              <div key={i} className="flex items-center gap-3 bg-surface-700 rounded-lg p-3">
                <span className="text-xl">{typeIcons[a.artifact_type] || '🎬'}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200">{a.description}</p>
                  <p className="text-xs text-gray-500 font-mono truncate">{a.file_path}</p>
                </div>
                {a.download_url && (
                  <a
                    href={a.download_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-secondary text-xs py-1.5 px-3 flex-shrink-0"
                  >
                    Download
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Logs */}
      {logs.length > 0 && (
        <div>
          <p className="label mb-2">Logs ({logs.length})</p>
          <div className="space-y-2">
            {logs.map((a, i) => (
              <div key={i} className="flex items-center gap-3 bg-surface-700 rounded-lg p-3">
                <span className="text-xl">📋</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-200">{a.description}</p>
                </div>
                {a.download_url && (
                  <a href={a.download_url} target="_blank" rel="noopener noreferrer"
                     className="btn-secondary text-xs py-1.5 px-3 flex-shrink-0">
                    View
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* No artifacts */}
      {artifacts.filter((a) => a.exists).length === 0 && (
        <p className="text-sm text-gray-500 text-center py-4">
          No artifacts available for this run yet.
        </p>
      )}
    </div>
  );
}
