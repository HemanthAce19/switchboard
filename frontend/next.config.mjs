/** @type {import('next').NextConfig} */
const nextConfig = {
  // "standalone" emits a self-contained server so the Docker image stays small.
  output: "standalone",
};

export default nextConfig;
