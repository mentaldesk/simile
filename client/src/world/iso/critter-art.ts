/** The colours critters use, from A1's palette in `server/simile/art/palette.py`. */
export const CRITTER_PALETTE = {
  ink: '#181425',
  night: '#262b44',
  slate: '#3a4466',
  steel: '#5a6988',
  concrete: '#8b9bb4',
  pavement: '#c0cbdc',
  white: '#ffffff',
  ice: '#a8e6f0',
  cream: '#ead4aa',
  sand: '#e4a672',
  tan: '#c28569',
  brown: '#b86f50',
  umber: '#733e39',
  amber: '#feae34',
  yellow: '#fee761',
  orange: '#f77622',
  green: '#3e8948',
  forest: '#265c42',
  navy: '#124e89',
} as const;

export type PaletteColour = keyof typeof CRITTER_PALETTE;

const OUTLINE: PaletteColour = 'ink';

export type CritterKind = 'duck' | 'heron' | 'ripple';

/** A kind's frames, in texture px, and the point on the water each is drawn at. */
export type FrameBox = { width: number; height: number; anchor: { x: number; y: number } };

export const CRITTER_BOXES: Record<CritterKind, FrameBox> = {
  duck: { width: 16, height: 12, anchor: { x: 8, y: 11 } },
  heron: { width: 24, height: 22, anchor: { x: 12, y: 19 } },
  ripple: { width: 16, height: 8, anchor: { x: 8, y: 4 } },
};

export const PLUMAGES = ['drake', 'hen'] as const;
export type Plumage = (typeof PLUMAGES)[number];

export const DUCK_POSES = ['paddle0', 'paddle1', 'dabble', 'preen0', 'preen1', 'tucked'] as const;
export type DuckPose = (typeof DUCK_POSES)[number];

export const HERON_POSES = ['stand', 'hunch', 'strike', 'fly0', 'fly1'] as const;
export type HeronPose = (typeof HERON_POSES)[number];

export const RIPPLES = ['koi', 'fish', 'ring1', 'ring2', 'ring3'] as const;
export type Ripple = (typeof RIPPLES)[number];

export type Side = 'left' | 'right';

export const duckFrame = (plumage: Plumage, pose: DuckPose, side: Side) => `${plumage}-${pose}-${side}`;
export const heronFrame = (pose: HeronPose, side: Side) => `heron-${pose}-${side}`;
export const rippleFrame = (ripple: Ripple) => `ripple-${ripple}`;

/** Drawn facing left. Body keys are outlined; `WATER` keys go under the outline, on the water. */
type Art = { rows: readonly string[]; key: Readonly<Record<string, PaletteColour>> };

const WATER: Readonly<Record<string, PaletteColour>> = { '~': 'ice', '^': 'white' };

const DRAKE_KEY = {
  g: 'green',
  G: 'forest',
  y: 'yellow',
  w: 'white',
  c: 'umber',
  b: 'pavement',
  B: 'concrete',
  v: 'navy',
  k: 'night',
} as const satisfies Record<string, PaletteColour>;

const HEN_KEY = {
  g: 'tan',
  G: 'umber',
  y: 'orange',
  w: 'tan',
  c: 'brown',
  b: 'sand',
  B: 'brown',
  v: 'navy',
  k: 'umber',
} as const satisfies Record<string, PaletteColour>;

const DUCK_ART: Record<DuckPose, readonly string[]> = {
  paddle0: [
    '................',
    '................',
    '................',
    '................',
    '....ggg.........',
    '..yyggG.........',
    '....gG..........',
    '....w.......k...',
    '...ccbbbbbbbk...',
    '..cccbbbvvBkk...',
    '...ccBBBBBBB....',
    '.~..........~~~.',
  ],
  paddle1: [
    '................',
    '................',
    '................',
    '................',
    '................',
    '....ggg.........',
    '..yyggG.........',
    '....wG......k...',
    '...ccbbbbbbbk...',
    '..cccbbbvvBkk...',
    '...ccBBBBBBB....',
    '..~..........~~.',
  ],
  dabble: [
    '................',
    '................',
    '................',
    '................',
    '................',
    '..........k.....',
    '.........kk.....',
    '........bBk.....',
    '.......bvBB.....',
    '......bbBBB.....',
    '.....BBBBB......',
    '...~~.....~~....',
  ],
  preen0: [
    '................',
    '................',
    '................',
    '................',
    '................',
    '.....ggg........',
    '....gGgyy.......',
    '.....wgG....k...',
    '...ccbbbbbbbk...',
    '..cccbbbvvBkk...',
    '...ccBBBBBBB....',
    '................',
  ],
  preen1: [
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '.....ggg........',
    '....gGggyy..k...',
    '...cwbbbbbbbk...',
    '..cccbbbvvBkk...',
    '...ccBBBBBBB....',
    '................',
  ],
  tucked: [
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '................',
    '....gggy........',
    '...cgGGbbbbbk...',
    '..cccbbbbbBkk...',
    '...ccBBBBBBB....',
    '................',
  ],
};

const HERON_KEY = {
  w: 'white',
  p: 'pavement',
  c: 'concrete',
  s: 'steel',
  k: 'night',
  y: 'amber',
  l: 'sand',
} as const satisfies Record<string, PaletteColour>;

const HERON_ART: Record<HeronPose, readonly string[]> = {
  stand: [
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '..........kkk...........',
    '.........wwwk...........',
    '.......yywwwp...........',
    '..........wpp...........',
    '..........pp............',
    '.........ppp............',
    '.........pppcc..........',
    '.........ppcccsc........',
    '..........pcssssk.......',
    '...........csssskk......',
    '............sskk........',
    '............l.l.........',
    '............l.l.........',
    '............l.l.........',
    '..........~~~.~~~.......',
    '........................',
    '........................',
  ],
  hunch: [
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '..........kkk...........',
    '.........wwwk...........',
    '.......yywwwpcc.........',
    '.........ppcccsc........',
    '.........ppccsssc.......',
    '..........pcssssk.......',
    '...........csssskk......',
    '............sskk........',
    '............l.l.........',
    '............l.l.........',
    '............l.l.........',
    '..........~~~.~~~.......',
    '........................',
    '........................',
  ],
  strike: [
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '..........pcc...........',
    '.........ppcccsc........',
    '........pp.cssssk.......',
    '.......pp...csssskk.....',
    '......wp....sskk........',
    '.....wwk....l.l.........',
    '....yyk.....l.l.........',
    '....y.......l.l.........',
    '..~~^~~...~~~.~~~.......',
    '........................',
    '........................',
  ],
  fly0: [
    '........................',
    '........................',
    '..........kss...........',
    '.........ksss...........',
    '.........ssss...........',
    '.........sssc...........',
    '..........scc...........',
    '..........ccc...........',
    '...kww...pccc...........',
    '.yywwwppccccccss........',
    '.....pppcccsss..llll....',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
  ],
  fly1: [
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '...kww..................',
    '.yywwwppccccccss........',
    '.....pppcccsss..llll....',
    '.........sssc...........',
    '.........ssss...........',
    '.........ksss...........',
    '..........kks...........',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
    '........................',
  ],
};

const RIPPLE_KEY = {
  o: 'orange',
  O: 'brown',
  w: 'white',
  s: 'steel',
  S: 'slate',
  p: 'pavement',
} as const satisfies Record<string, PaletteColour>;

const RIPPLE_ART: Record<Ripple, readonly string[]> = {
  koi: [
    '................',
    '................',
    '.......o........',
    '......oO.^......',
    '.....wo.........',
    '....~~~~~.......',
    '................',
    '................',
  ],
  fish: [
    '................',
    '................',
    '.......s........',
    '......sS.^......',
    '.....ps.........',
    '....~~~~~.......',
    '................',
    '................',
  ],
  ring1: [
    '................',
    '................',
    '.......~~.......',
    '......~..~......',
    '......~..~......',
    '.......~~.......',
    '................',
    '................',
  ],
  ring2: [
    '................',
    '......~~~~......',
    '....~~....~~....',
    '...~........~...',
    '....~~....~~....',
    '......~~~~......',
    '................',
    '................',
  ],
  ring3: [
    '.....~~~..~~....',
    '...~~........~..',
    '.~............~.',
    '................',
    '.~............~.',
    '...~~........~~.',
    '.....~~..~~~....',
    '................',
  ],
};

type Rgba = [r: number, g: number, b: number, a: number];

const rgba = (colour: PaletteColour): Rgba => {
  const hex = CRITTER_PALETTE[colour];
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)).concat(255) as Rgba;
};

type FramePixels = (PaletteColour | undefined)[];

function drawArt({ rows, key }: Art, { width, height }: FrameBox, outlined: boolean): FramePixels {
  if (rows.length !== height || rows.some((row) => row.length !== width)) {
    throw new RangeError(`Art isn't ${width} × ${height}: ${rows.join('/')}`);
  }
  const pixels: FramePixels = new Array(width * height).fill(undefined);
  rows.forEach((row, y) =>
    [...row].forEach((char, x) => {
      if (!WATER[char]) pixels[y * width + x] = key[char];
    }),
  );
  if (outlined) {
    const body = [...pixels];
    const solid = (x: number, y: number) =>
      x >= 0 && y >= 0 && x < width && y < height && body[y * width + x] !== undefined;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        if (body[y * width + x] !== undefined) continue;
        if (solid(x - 1, y) || solid(x + 1, y) || solid(x, y - 1) || solid(x, y + 1)) {
          pixels[y * width + x] = OUTLINE;
        }
      }
    }
  }
  rows.forEach((row, y) =>
    [...row].forEach((char, x) => {
      if (WATER[char] && pixels[y * width + x] === undefined) pixels[y * width + x] = WATER[char];
    }),
  );
  return pixels;
}

const mirrored = (pixels: FramePixels, width: number): FramePixels =>
  pixels.map((_, i) => pixels[i - (i % width) + (width - 1 - (i % width))]);

export type SheetFrame = { name: string; kind: CritterKind; x: number; y: number };

export type CritterSheet = {
  width: number;
  height: number;
  rgba: Uint8ClampedArray<ArrayBuffer>;
  frames: SheetFrame[];
};

type Drawn = { name: string; kind: CritterKind; pixels: FramePixels };

function sided(name: (side: Side) => string, kind: CritterKind, pixels: FramePixels): Drawn[] {
  return [
    { name: name('left'), kind, pixels },
    { name: name('right'), kind, pixels: mirrored(pixels, CRITTER_BOXES[kind].width) },
  ];
}

function drawnRows(): Drawn[][] {
  const ducks = PLUMAGES.map((plumage) =>
    DUCK_POSES.flatMap((pose) => {
      const key = plumage === 'drake' ? DRAKE_KEY : HEN_KEY;
      const pixels = drawArt({ rows: DUCK_ART[pose], key }, CRITTER_BOXES.duck, true);
      return sided((side) => duckFrame(plumage, pose, side), 'duck', pixels);
    }),
  );
  const heron = HERON_POSES.flatMap((pose) =>
    sided(
      (side) => heronFrame(pose, side),
      'heron',
      drawArt({ rows: HERON_ART[pose], key: HERON_KEY }, CRITTER_BOXES.heron, true),
    ),
  );
  const ripples = RIPPLES.map((ripple) => ({
    name: rippleFrame(ripple),
    kind: 'ripple' as const,
    pixels: drawArt(
      { rows: RIPPLE_ART[ripple], key: RIPPLE_KEY },
      CRITTER_BOXES.ripple,
      ripple === 'koi' || ripple === 'fish',
    ),
  }));
  return [...ducks, heron, ripples];
}

export function critterSheet(): CritterSheet {
  const rows = drawnRows();
  const rowWidth = (row: Drawn[]) => row.reduce((sum, { kind }) => sum + CRITTER_BOXES[kind].width, 0);
  const width = Math.max(...rows.map(rowWidth));
  const height = rows.reduce((sum, row) => sum + CRITTER_BOXES[row[0].kind].height, 0);
  const rgbaOut = new Uint8ClampedArray(width * height * 4);
  const frames: SheetFrame[] = [];
  let top = 0;
  for (const row of rows) {
    let left = 0;
    for (const { name, kind, pixels } of row) {
      const box = CRITTER_BOXES[kind];
      pixels.forEach((colour, i) => {
        if (!colour) return;
        const at = ((top + Math.floor(i / box.width)) * width + left + (i % box.width)) * 4;
        rgbaOut.set(rgba(colour), at);
      });
      frames.push({ name, kind, x: left, y: top });
      left += box.width;
    }
    top += CRITTER_BOXES[row[0].kind].height;
  }
  return { width, height, rgba: rgbaOut, frames };
}
