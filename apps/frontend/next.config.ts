import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

const apiOrigin = (() => {
  try { return process.env.NEXT_PUBLIC_API_URL ? new URL(process.env.NEXT_PUBLIC_API_URL).origin : ""; } catch { return ""; }
})();

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "img-src 'self' data: blob: https:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  // React dev tooling needs eval; production never does.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  // The browser calls the API directly (cart/availability checks), so its exact origin must be allowed even when it is plain http (local, internal).
  `connect-src 'self' https: ${apiOrigin}${isDev ? " ws://localhost:* ws://127.0.0.1:*" : ""}`.replace(/ +/g, " ").trim(),
].join("; ");

const nextConfig: NextConfig = {
  poweredByHeader: false,
  reactCompiler: true,
  output: "standalone",
  images: {
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 60 * 60 * 24,
    remotePatterns: [
      { protocol: "https", hostname: "**" },
    ],
  },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        { key: "Content-Security-Policy", value: csp },
      ],
    }];
  },
};

export default nextConfig;
