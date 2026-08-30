import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const BACKEND = process.env.BACKEND_URL || 'http://backend:8001';

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const target = `${BACKEND.replace(/\/$/, '')}/api/${path.map(segment => encodeURIComponent(segment)).join('/')}${request.nextUrl.search}`;
  const headers = new Headers(request.headers);

  // These hop-by-hop headers describe the browser-to-Next connection and
  // must be regenerated for the Next-to-backend request.
  headers.delete('host');
  headers.delete('content-length');
  headers.delete('connection');

  const body = request.method === 'GET' || request.method === 'HEAD'
    ? undefined
    : await request.arrayBuffer();

  try {
    const response = await fetch(target, {
      method: request.method,
      headers,
      body: body && body.byteLength > 0 ? body : undefined,
      redirect: 'manual',
      cache: 'no-store',
    });

    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete('content-length');
    responseHeaders.delete('content-encoding');

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error('API proxy error', {
      method: request.method,
      path: request.nextUrl.pathname,
      message: error instanceof Error ? error.message : String(error),
    });
    return NextResponse.json(
      { detail: 'Backend API inaccessible depuis le proxy PWA.' },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const HEAD = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
