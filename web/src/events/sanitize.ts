/** Display sanitization for untrusted tool output, posts, and descriptions. Not a scorer. */

const HIDDEN_KEYS = new Set([
  "reasoning",
  "chain_of_thought",
  "chainOfThought",
  "thinking",
  "cot",
  "provider_key",
  "providerKey",
  "api_key",
  "apiKey",
  "authorization",
  "secret_key",
  "app_secret",
]);

const MAX_TEXT = 12_000;

/** Strip control and bidi characters. React text nodes escape HTML; we still flatten spoofing. */
function isStrippedChar(code: number): boolean {
  if (code <= 8 || code === 11 || code === 12 || (code >= 14 && code <= 31) || code === 127) return true;
  if (code >= 0x200b && code <= 0x200f) return true;
  if (code >= 0x202a && code <= 0x202e) return true;
  if (code >= 0x2066 && code <= 0x2069) return true;
  return code === 0xfeff;
}

export function sanitizeText(input: string, max = MAX_TEXT): string {
  const cleaned = Array.from(input.normalize("NFC"))
    .filter((char) => !isStrippedChar(char.codePointAt(0) ?? 0))
    .join("");
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max)}\n…[truncated for display]`;
}

export function isHiddenKey(key: string): boolean {
  return HIDDEN_KEYS.has(key);
}

export function sanitizeValue(value: unknown, depth = 0): unknown {
  if (depth > 8) return "[max depth]";
  if (typeof value === "string") return sanitizeText(value);
  if (typeof value === "number" || typeof value === "boolean" || value === null) return value;
  if (Array.isArray(value)) return value.map((item) => sanitizeValue(item, depth + 1));
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value)) {
      if (isHiddenKey(key)) continue;
      out[key] = sanitizeValue(inner, depth + 1);
    }
    return out;
  }
  return sanitizeText(String(value));
}

export function prettySanitized(value: unknown): string {
  return sanitizeText(JSON.stringify(sanitizeValue(value), null, 2) ?? "null");
}
