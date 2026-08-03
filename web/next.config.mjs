/** @type {import("next").NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  distDir: process.env.COURT4_NEXT_DIST_DIR ?? ".next",
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
