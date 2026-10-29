/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DEFAULT_MODE?: string;
}

declare module "*.jsonl?raw" {
  const src: string;
  export default src;
}
