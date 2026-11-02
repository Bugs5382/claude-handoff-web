// The page file as GET /_page/<folder>/<slug> returns it. See PAGE-FILE.md.
export type Block = Record<string, unknown>;

export interface ItemDef {
  id: string;
  title: string;
  type?: string;
  section?: string;
  body?: Block[];
  howto?: Block[];
  answers?: string[];
  skip?: boolean;
  suggested?: string;
}

export interface Answer { answer: string; note?: string; at?: string; by?: string }

export interface Round {
  round: number;
  answers: Record<string, Answer>;
  reopened?: Record<string, string>;
  awaiting?: number;
  held?: number[];
}

export interface PageDoc {
  rev: number;
  kind: string;
  title: string;
  summary?: string;
  build?: string | null;
  items: ItemDef[];
  rounds: Round[];
  submissions: { n: number; items: string[]; kind: string; at: string; to?: string; state?: string }[];
  thread: Record<string, { from: string; at: string; text: string; action?: string; reason?: string }[]>;
}

export interface ItemState { answer: string; hidden: boolean; reopened: string | null; round: number | null }

export interface PageData {
  page: PageDoc;
  states: Record<string, ItemState>;
  route: { to: string; mode: string };
  listening: boolean;
  diffs?: Record<string, string>;
}

export interface Local { answer: string; note: string }
