import type { NextConfig } from "next";
import { imgSrc, parseImageHosts, remoteImagePatterns } from "./src/lib/image-hosts";

const imageHosts = parseImageHosts(process.env.IMAGE_ALLOWED_HOSTS);

const nextConfig: NextConfig = {
  reactCompiler: true,
  output: "standalone",
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: remoteImagePatterns(imageHosts),
  },
  async headers() {
    return [{
      source: "/(.*)",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        { key: "Content-Security-Policy", value: `default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; ${imgSrc(imageHosts)}; font-src 'self' data:; style-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/style; script-src 'self' 'unsafe-inline' https://accounts.google.com/gsi/client; frame-src https://accounts.google.com/gsi/; connect-src 'self' https: http://localhost:* http://127.0.0.1:*` },
      ],
    }];
  },
};

export default nextConfig;
