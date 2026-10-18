type Value = string | number | boolean | null | undefined | ((event: Event) => void);
export type Child = Node | string | null | undefined | false;

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Record<string, Value> = {},
  ...children: (Child | Child[])[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (typeof value === 'function') node.addEventListener(name.slice(2), value);
    else if (name in node && !name.includes('-')) Reflect.set(node, name, value);
    else node.setAttribute(name, value === true ? '' : String(value));
  }
  for (const child of children.flat())
    if (child !== null && child !== undefined && child !== false) node.append(child);
  return node;
}

export function labelled(label: string, control: HTMLElement, hint?: Child): HTMLLabelElement {
  return h(
    'label',
    { className: 'creator-field' },
    h('span', {}, label),
    control,
    hint ? h('small', {}, hint) : null,
  );
}

export function textInput(
  value: string,
  onInput: (value: string) => void,
  props: Record<string, Value> = {},
): HTMLInputElement {
  return h('input', {
    type: 'text',
    value,
    oninput: (event) => onInput((event.target as HTMLInputElement).value),
    ...props,
  });
}

export function textArea(
  value: string,
  onInput: (value: string) => void,
  props: Record<string, Value> = {},
): HTMLTextAreaElement {
  const area = h('textarea', {
    oninput: (event) => onInput((event.target as HTMLTextAreaElement).value),
    ...props,
  });
  area.value = value;
  return area;
}

export function select<T extends string>(
  value: T | '',
  options: readonly (readonly [T | '', string])[],
  onChange: (value: T | '') => void,
  props: Record<string, Value> = {},
): HTMLSelectElement {
  const control = h(
    'select',
    {
      onchange: (event) => onChange((event.target as HTMLSelectElement).value as T | ''),
      ...props,
    },
    options.map(([option, text]) => h('option', { value: option }, text)),
  );
  control.value = value;
  return control;
}

export function button(
  text: Child,
  onClick: () => void,
  props: Record<string, Value> = {},
): HTMLButtonElement {
  return h('button', { type: 'button', onclick: onClick, ...props }, text);
}

export function capitalise(text: string): string {
  return text ? text[0].toUpperCase() + text.slice(1) : text;
}

export function humanise(key: string): string {
  return capitalise(key.replaceAll('_', ' '));
}

export function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
