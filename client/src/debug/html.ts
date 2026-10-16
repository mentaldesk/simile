export class Html {
  readonly text: string;

  constructor(text: string) {
    this.text = text;
  }
}

type Part = Html | string | number | boolean | null | undefined | readonly Part[];

/** A template whose interpolations are escaped, unless they're `Html` themselves. */
export function html(strings: TemplateStringsArray, ...parts: Part[]): Html {
  return new Html(strings.reduce((out, string, i) => out + render(parts[i - 1]) + string));
}

function render(part: Part): string {
  if (part instanceof Html) return part.text;
  if (Array.isArray(part)) return part.map(render).join('');
  if (part === null || part === undefined || part === false) return '';
  return String(part).replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
}
