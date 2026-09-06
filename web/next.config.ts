import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  experimental: {
    // Catalog accepts evidence files up to 10 MiB. Leave a little room for the
    // remaining multipart fields while keeping the Server Action bounded.
    serverActions: { bodySizeLimit: "11mb" },
  },
};

export default nextConfig;
