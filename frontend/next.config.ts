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

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  async headers() {
    return [{source: "/:path*", headers: securityHeaders}];
  },
};

export default nextConfig;
