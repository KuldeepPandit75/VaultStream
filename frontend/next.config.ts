import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    // Posters and backdrops are served from TMDB's image CDN.
    remotePatterns: [
      {
        protocol: "https",
        hostname: "image.tmdb.org",
        pathname: "/t/p/**",
      },
    ],
    // Poster grid renditions; keeps the optimizer from generating dozens of sizes.
    imageSizes: [96, 128, 185, 256],
    deviceSizes: [640, 750, 828, 1080, 1200, 1920, 2048],
  },
};

export default nextConfig;
