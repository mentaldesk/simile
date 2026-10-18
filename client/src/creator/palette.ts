import type { Accessory, Appearance, Build, HairStyle } from './character';

export const PALETTE: Record<string, string> = {
  ink: '#181425',
  night: '#262b44',
  slate: '#3a4466',
  steel: '#5a6988',
  concrete: '#8b9bb4',
  pavement: '#c0cbdc',
  white: '#ffffff',
  ice: '#a8e6f0',
  cream: '#ead4aa',
  peach: '#e8b796',
  sand: '#e4a672',
  tan: '#c28569',
  brown: '#b86f50',
  umber: '#733e39',
  espresso: '#3e2731',
  maroon: '#a22633',
  red: '#e43b44',
  orange: '#f77622',
  amber: '#feae34',
  yellow: '#fee761',
  lime: '#63c74d',
  green: '#3e8948',
  forest: '#265c42',
  deep: '#193c3e',
  navy: '#124e89',
  blue: '#0099db',
  cyan: '#2ce8f5',
  plum: '#68386c',
  magenta: '#b55088',
  pink: '#f6757a',
  neon: '#ff4fa8',
  violet: '#8a5cf6',
};

export const SKIN_TONES = ['cream', 'peach', 'sand', 'tan', 'brown', 'umber'];
export const CLOTH_COLOURS = Object.keys(PALETTE).filter((name) => name !== 'ink');

export const HAIR_STYLES: HairStyle[] = [
  'bald',
  'buzz',
  'short',
  'curly',
  'bob',
  'long',
  'ponytail',
  'bun',
];
export const BUILDS: Build[] = ['slim', 'average', 'broad'];
export const ACCESSORIES: Accessory[] = [
  'glasses',
  'sunglasses',
  'cap',
  'beanie',
  'headphones',
  'scarf',
  'backpack',
  'apron',
];

export const DEFAULT_LOOK: Appearance = {
  skin: '#e4a672',
  hair_style: 'short',
  hair_colour: '#3e2731',
  top_colour: '#0099db',
  bottom_colour: '#3a4466',
  shoe_colour: '#ffffff',
  build: 'average',
  accessories: ['backpack'],
};

export function nearest(hex: string, choices: string[] = CLOTH_COLOURS): string {
  const target = lab(hex);
  const distance = (name: string) =>
    lab(PALETTE[name]).reduce((total, c, i) => total + (c - target[i]) ** 2, 0);
  return choices.reduce((best, name) => (distance(name) < distance(best) ? name : best));
}

function lab(hex: string): [number, number, number] {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const fx = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047);
  const fy = f(0.2126 * r + 0.7152 * g + 0.0722 * b);
  const fz = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883);
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
}
