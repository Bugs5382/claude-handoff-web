// The page file as GET /_page/<folder>/<slug> returns it. See PAGE-FILE.md.
export type Block = Record<string, unknown>;
export interface Field { name: string; type?: string; rule?: string }

export interface ItemChoice { value: string; label: string; description?: string; recommended?: boolean }

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
  steps?: string[];
  checkpoint?: string;
  dependsOn?: string[];
  blockedBy?: string;
  choices?: ItemChoice[];
  multi?: boolean;
  images?: { src: string; alt?: string; caption?: string }[];
  fields?: Field[];
  forms?: { name: string; fields?: Field[] }[];
}

export interface Answer { answer: string; note?: string; other?: string; at?: string; by?: string }
export interface Handled extends Answer { handled: string; via: string; blocker?: boolean }

export interface Round {
  round: number;
  build?: string | null;
  closed?: string | null;
  results?: string;
  restart?: string;
  answers: Record<string, Answer>;
  reopened?: Record<string, string>;
  handled?: Record<string, Handled[]>;
  checkpoints?: Record<string, string>;
  awaiting?: number;
  held?: number[];
}

export interface Submission { n: number; items: string[]; kind: string; at: string; to?: string; state?: string; takenAt?: string; handled?: string; round: number }
export interface Reply { from: string; at: string; text: string; action?: string; reason?: string; ref?: string }

export interface PhaseDef { id: string; title: string; goal?: string; dependsOn?: string[] }
export interface PhaseState { items: string[]; closed: boolean; blocked: string | null }

export interface EmailVersion { n: number; at: string; from: string; to?: string; subject?: string; body: string; ask?: string; tone?: string; change?: string; basedOn?: number }

export interface PageDoc {
  rev: number;
  kind: string;
  title: string;
  summary?: string;
  build?: string | null;
  options?: { choices: { value: string; label: string }[]; default?: string };
  phases?: PhaseDef[];
  drafts?: boolean;
  template?: string;
  deck?: boolean;
  emails?: Record<string, EmailVersion[]>;
  items: ItemDef[];
  rounds: Round[];
  submissions: Submission[];
  thread: Record<string, Reply[]>;
}

export interface ItemState { answer: string; hidden: boolean; reopened: string | null; round: number | null }

export interface PageData {
  page: PageDoc;
  phases: Record<string, PhaseState>;
  states: Record<string, ItemState>;
  route: { to: string; mode: string };
  listening: boolean;
  diffs?: Record<string, string>;
}

/** One item's answer in this tab: v is yes, no, chg, skip or a choice, n the note, a a question's answer. */
export interface Local { v?: string; n?: string; a?: string; o?: string; locked?: boolean; blocker?: boolean }
export type Locals = Record<string, Local>;
