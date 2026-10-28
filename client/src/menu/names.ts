const FIRST = [
  'Ash',
  'Brindle',
  'Cinder',
  'Copper',
  'Ember',
  'Flint',
  'Hollow',
  'Kiln',
  'Lantern',
  'Mill',
  'Rook',
  'Slate',
  'Tallow',
  'Wren',
];

const LAST = ['Close', 'Court', 'End', 'Lane', 'Row', 'Street', 'Walk', 'Yard'];

/** A street name for a new world that none of `taken` has. */
export function suggestName(taken: readonly string[], random: () => number = Math.random): string {
  const pick = <T>(list: readonly T[]) => list[Math.floor(random() * list.length)];
  const used = new Set(taken.map((name) => name.toLowerCase()));
  for (let tries = 0; tries < 50; tries++) {
    const name = `${pick(FIRST)} ${pick(LAST)}`;
    if (!used.has(name.toLowerCase())) return name;
  }
  return `${pick(FIRST)} ${pick(LAST)} ${taken.length + 1}`;
}
