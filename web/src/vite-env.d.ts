/// <reference types="vite/client" />

declare module "*.jsonl?raw" {
  const src: string;
  export default src;
}
