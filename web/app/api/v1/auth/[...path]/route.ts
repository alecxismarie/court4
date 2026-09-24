import { proxyAuth } from "@/lib/auth-proxy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function handle(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxyAuth(request, (await context.params).path);
}

export { handle as GET, handle as POST, handle as DELETE };
