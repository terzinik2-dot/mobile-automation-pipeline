import { auth } from '@clerk/nextjs/server';
import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const { userId } = auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const runId = params.id;

  // Handle special sub-paths
  const url = new URL(req.url);
  const isArtifacts = url.pathname.endsWith('/artifacts');

  try {
    const endpoint = isArtifacts
      ? `${API_URL}/api/v1/runs/${runId}/artifacts`
      : `${API_URL}/api/v1/runs/${runId}`;

    const resp = await fetch(endpoint);
    if (resp.status === 404) {
      return NextResponse.json({ detail: 'Not found' }, { status: 404 });
    }
    const data = await resp.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error(`[API] GET /runs/${runId} error:`, err);
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 503 });
  }
}

export async function DELETE(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const { userId } = auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const resp = await fetch(`${API_URL}/api/v1/runs/${params.id}`, {
      method: 'DELETE',
    });
    const data = await resp.json();
    return NextResponse.json(data);
  } catch (err) {
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 503 });
  }
}
