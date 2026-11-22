import type { NextConfig } from "next";

const apiPort = process.env.REPROSTAMP_API_PORT ?? "8000";
if (!/^\d{1,5}$/.test(apiPort)) throw new Error("REPROSTAMP_API_PORT must be a loopback API port.");

export default {
  agentRules: false,
  devIndicators: false,
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `http://127.0.0.1:${apiPort}/api/v1/:path*` }];
  },
} satisfies NextConfig;
