// The browser only ever calls /api/*; Next.js forwards it to the backend (the HF Space),
// so there's no CORS and the backend URL lives in one place.
// Local dev: BACKEND_URL=http://localhost:8000 npm run dev
const BACKEND_URL = (process.env.BACKEND_URL || "https://happynishh-batchmate.hf.space").replace(/\/$/, "");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // No ESLint dependency in this project; don't let a missing linter block a Vercel build.
  eslint: { ignoreDuringBuilds: true },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/:path*` }];
  },
};

export default nextConfig;
