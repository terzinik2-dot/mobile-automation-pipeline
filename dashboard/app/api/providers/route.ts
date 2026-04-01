import { auth } from '@clerk/nextjs/server';
import { NextRequest, NextResponse } from 'next/server';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(req: NextRequest) {
  const { userId } = auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const resp = await fetch(`${API_URL}/api/v1/providers`);
    const data = await resp.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error('[API] GET /providers error:', err);
    // Return hardcoded fallback if backend is unavailable
    return NextResponse.json({
      providers: [
        {
          provider_id: 'local',
          name: 'Local ADB Device',
          description: 'Local Android device via ADB',
          configured: true,
          required_env_vars: [],
        },
        {
          provider_id: 'browserstack',
          name: 'BrowserStack',
          description: 'Cloud real device testing',
          configured: false,
          required_env_vars: ['BROWSERSTACK_USERNAME', 'BROWSERSTACK_ACCESS_KEY'],
        },
        {
          provider_id: 'aws_device_farm',
          name: 'AWS Device Farm',
          description: 'AWS cloud devices',
          configured: false,
          required_env_vars: ['AWS_ACCESS_KEY_ID', 'AWS_DEVICE_FARM_PROJECT_ARN'],
        },
      ],
    });
  }
}
