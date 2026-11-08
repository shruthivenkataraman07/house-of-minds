import type { NextConfig } from "next";

// Static export: FastAPI serves web/out and the /api/v1 routes from one origin.
const nextConfig: NextConfig = {
  output: "export",
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
