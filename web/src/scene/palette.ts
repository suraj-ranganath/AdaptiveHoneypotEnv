/** Keep these in sync with the custom properties in styles.css. */
export const ATTACKER_COLOR = ["#d4532b", "#0f766e", "#334e9a"] as const;
export const ATTACKER_HEX = [0xd4532b, 0x0f766e, 0x334e9a] as const;

export const BRASS = "#8a6a12";
export const BRASS_HEX = 0x8a6a12;
export const ALERT_HEX = 0xc2410c;
export const COMPROMISE_HEX = 0x8f1d2c;

export function attackerColor(index: number): string {
  return ATTACKER_COLOR[index] ?? ATTACKER_COLOR[0];
}
