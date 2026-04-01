import { auth } from '@clerk/nextjs/server';
import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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

    const resp = await fetch(`${API_URL}/api/v1/runs?${params}`);
    const data = await resp.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: 'Backend unavailable', runs: [], total: 0 }, { status: 503 });
  }
}
