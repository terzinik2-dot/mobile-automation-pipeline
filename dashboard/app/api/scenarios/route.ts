import { auth } from '@clerk/nextjs/server';
import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const { userId } = auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const body = await req.json();
    const resp = await fetch(`${API_URL}/api/v1/scenarios/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      return NextResponse.json(
        { error: errData.detail || 'Backend error' },
        { status: resp.status }
      );
    }

    const data = await resp.json();
    return NextResponse.json(data, { status: 202 });
  } catch (err) {
    console.error('[API] POST /scenarios error:', err);
    return NextResponse.json(
      { error: 'Failed to connect to backend' },
      { status: 503 }
    );
  }
}

export async function GET(req: NextRequest) {
  const { userId } = auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const limit = searchParams.get('limit') || '20';
  const offset = searchParams.get('offset') || '0';
  const status = searchParams.get('status') || '';

  try {
    const params = new URLSearchParams({ limit, offset });
    if (status) params.append('status', status);

    const resp = await fetch(`${API_URL}/api/v1/runs?${params}`, {
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await resp.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error('[API] GET /scenarios error:', err);
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 503 });
  }
}
