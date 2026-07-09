import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  serverExternalPackages: ['@prisma/client', 'prisma'],
  allowedDevOrigins: ['169.254.83.107', 'localhost'],
};

export default nextConfig;
