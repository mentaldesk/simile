import { html, type Html } from './html';
import type {
  ConversationState,
  IntentionRow,
  MemoryRow,
  NpcState,
  Reason,
  RelationshipRow,
} from './state';

export type PanelData = {
  npcId?: string;
  state?: Partial<NpcState>;
  names: ReadonlyMap<string, string>;
};

const TOP_OPTIONS = 5;
const HINT = html`<footer>\` closes · click another NPC to switch</footer>`;

export function renderPanel({ npcId, state, names }: PanelData): string {
  const nameOf = (id: string) => names.get(id) ?? id;
  if (!npcId) {
    return html`<p class="debug-hint">Click an NPC to see inside their head.</p>${HINT}`.text;
  }
  if (!state) {
    return html`<header><b>${nameOf(npcId)}</b></header>
      <p class="debug-hint">Waiting for the server…</p>${HINT}`.text;
  }
  const firstName = (id: string) => (id === npcId ? state.name : nameOf(id))?.split(' ')[0] ?? id;
  return html`
    <header>
      <b>${state.name ?? nameOf(npcId)}</b> <span>${state.occupation}</span>
      ${state.time && html`<time>${state.time.slice(11, 19)}</time>`}
    </header>
    ${section('Goal', goal(state))}
    ${state.needs && section('Needs', bars(state.needs))}
    ${state.values && section('Top values', bars(state.values))}
    ${state.options && section('Last decision', options(state.options, state.reasons, nameOf))}
    ${state.intentions && section('Intentions', intentions(state.intentions, nameOf, state.time))}
    ${state.relationships && section('Relationships', table(state.relationships, nameOf))}
    ${state.memories && section('Memories', memories(state.memories, state.time))}
    ${'conversation' in state && section('Conversation', talk(state.conversation, firstName))}
    ${HINT}`.text;
}

function section(title: string, body: Html): Html {
  return html`<section><h3>${title}</h3>${body}</section>`;
}

function goal(state: Partial<NpcState>): Html {
  const notes = [
    state.walking && 'walking',
    state.paused && 'paused',
    state.since && `since ${clock(state.since)}`,
    state.until && `until ${clock(state.until)}`,
  ].filter(Boolean);
  return html`<p><b>${state.goal ?? '?'}</b> ${notes.join(' · ')}</p>`;
}

function bars(scores: Record<string, number>): Html {
  return html`<table class="debug-bars">
    ${Object.entries(scores).map(
      ([name, score]) => html`<tr>
        <th>${name}</th>
        <td><span class="debug-bar"><i style="width: ${percent(score)}%"></i></span></td>
        <td>${score.toFixed(2)}</td>
      </tr>`,
    )}
  </table>`;
}

function options(
  scores: Record<string, number>,
  reasons: Record<string, Reason> | undefined,
  nameOf: (id: string) => string,
): Html {
  const best = Object.entries(scores)
    .sort(([, a], [, b]) => b - a)
    .slice(0, TOP_OPTIONS);
  if (best.length === 0) return html`<p class="debug-hint">None yet.</p>`;
  return html`<ol class="debug-options">
    ${best.map(([option, score]) => {
      const reason = reasons?.[option];
      const why = reason && `${signed(reason.bonus)} ${said(reason, nameOf)}`;
      return html`<li>${option} <small>${score.toFixed(2)}</small>${why && html` <em>${why}</em>`}</li>`;
    })}
  </ol>`;
}

function intentions(
  rows: IntentionRow[],
  nameOf: (id: string) => string,
  now: string | undefined,
): Html {
  if (rows.length === 0) return html`<p class="debug-hint">None.</p>`;
  return html`<ul class="debug-intentions">
    ${rows.map((row) => {
      const notes = [
        row.target && `at ${nameOf(row.target)}`,
        `due ${when(row.due, now)}`,
        `expires ${when(row.expires, now)}`,
        row.following === false && 'letting it slide',
      ].filter(Boolean);
      return html`<li>
        <em>${row.kind}</em> ${said(row, nameOf)} <small>${notes.join(' · ')}</small>
      </li>`;
    })}
  </ul>`;
}

function said(row: IntentionRow, nameOf: (id: string) => string): string {
  const told = row.promised_to.map(nameOf).join(', ');
  return told ? `promised ${told}: ${row.description}` : `meant to: ${row.description}`;
}

function table(rows: RelationshipRow[], nameOf: (id: string) => string): Html {
  if (rows.length === 0) return html`<p class="debug-hint">Nobody yet.</p>`;
  return html`<table class="debug-relationships">
    <tr><th></th><th>like</th><th>trust</th><th>resp</th><th>fam</th></tr>
    ${rows.map(
      (row) => html`<tr>
          <th>${nameOf(row.about)}</th>
          <td>${row.like.toFixed(2)}</td>
          <td>${row.trust.toFixed(2)}</td>
          <td>${row.respect.toFixed(2)}</td>
          <td>${row.familiarity.toFixed(2)}</td>
        </tr>
        ${row.flags.length > 0 && flags(row.flags)}`,
    )}
  </table>`;
}

function flags(rows: RelationshipRow['flags']): Html {
  return html`<tr class="debug-flags">
    <td colspan="5">
      ${rows.map(
        ({ kind, description, open }) =>
          html`<span class="${open ? 'open' : 'resolved'}">${kind}: ${description}</span> `,
      )}
    </td>
  </tr>`;
}

function memories(rows: MemoryRow[], now: string | undefined): Html {
  if (rows.length === 0) return html`<p class="debug-hint">Nothing yet.</p>`;
  return html`<ul class="debug-memories">
    ${rows.map(
      (memory) => html`<li>
        <time>${when(memory.timestamp, now)}</time> <em>${memory.kind}</em> ${memory.content}
        <small>salience ${memory.salience.toFixed(2)} · feeling ${signed(memory.valence)}</small>
      </li>`,
    )}
  </ul>`;
}

function talk(
  conversation: ConversationState | null | undefined,
  firstName: (id: string) => string,
): Html {
  if (!conversation) return html`<p class="debug-hint">Not talking.</p>`;
  const { talking_to, engagement, leaving, lines } = conversation;
  return html`<p>
      With <b>${firstName(talking_to)}</b> · engagement ${engagement.toFixed(2)}
      ${leaving && ' · saying goodbye'}
    </p>
    <ol class="debug-transcript">
      ${lines.map((line) => html`<li><b>${firstName(line.speaker)}</b> ${line.text}</li>`)}
    </ol>`;
}

const percent = (score: number) => Math.round(Math.min(Math.max(score, 0), 1) * 100);
const signed = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
const clock = (iso: string) => iso.slice(11, 16);
const when = (iso: string, now: string | undefined) =>
  now && iso.slice(0, 10) === now.slice(0, 10) ? clock(iso) : `${iso.slice(5, 10)} ${clock(iso)}`;
