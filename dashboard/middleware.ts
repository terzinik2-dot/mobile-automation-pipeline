import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// If Clerk keys are present — use Clerk auth. Otherwise — pass through (demo mode).
const hasClerk =
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY &&
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY !== '';

export async function middleware(req: NextRequest) {
  if (!hasClerk) {
    // Demo mode: no auth required
    return NextResponse.next();
  }

  // Lazy-load Clerk only when keys are present
  const { clerkMiddleware, createRouteMatcher } = await import('@clerk/nextjs/server');
  const isPublicRoute = createRouteMatcher(['/', '/sign-in(.*)', '/sign-up(.*)', '/api/health']);
  return clerkMiddleware((auth, request) => {
    if (!isPublicRoute(request)) {
      auth().protect();
    }
  })(req, {} as any);
}

export const config = {
  matcher: [
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    '/(api|trpc)(.*)',
  ],
};
