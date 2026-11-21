import type {NextConfig} from "next";

/**
 * Defensive headers for every page. The Content-Security-Policy here only covers what needs no
 * inline-script handling (framing, <base>, plugins, form targets); a full script policy can be
 * added later with nonces once the pages are measured in the browser's CSP report-only mode.
 */
export const securityHeaders = [
  {key: "X-Content-Type-Options", value: "nosniff"},
  {key: "X-Frame-Options", value: "DENY"},
  {key: "Referrer-Policy", value: "strict-origin-when-cross-origin"},
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  {
    key: "Content-Security-Policy",
    value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'",
  },
  {key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains"},
];

/**
 * A Production build without NEXT_PUBLIC_API_URL would quietly talk to http://127.0.0.1:8000 (the
 * development default in lib/chatApi.ts) and the chat would be dead on the live site. Fail the build
 * instead. Only Vercel's Production environment is checked, so local builds and previews are free.
 */
export function assertBuildEnv(env: Record<string, string | undefined>): void {
  if (env.VERCEL_ENV !== "production") return;
  const url = env.NEXT_PUBLIC_API_URL;
  if (!url) throw new Error("NEXT_PUBLIC_API_URL is not set for this Production build (Vercel > Settings > Environment Variables).");
  if (!url.startsWith("https://")) throw new Error(`NEXT_PUBLIC_API_URL must be an https:// URL, got ${url}`);
  if (/localhost|127\.0\.0\.1/.test(url)) throw new Error(`NEXT_PUBLIC_API_URL points at ${url}: use the deployed backend.`);
}

assertBuildEnv(process.env);

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async headers() {
    return [{source: "/:path*", headers: securityHeaders}];
  },
};

export default nextConfig;
