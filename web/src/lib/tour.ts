import { driver } from "driver.js";
import css from "driver.js/dist/driver.css?inline";

export interface TourStep {
  /** A CSS selector for the control it points at. A step whose control isn't on the page is left out. */
  element: string;
  title: string;
  text: string;
}

const ANSWER: TourStep = { element: ".rvcard:not(.settled) .seg", title: "Answer each item", text: "Pick an answer. Pressing it again clears it. It saves as you go." };
const COUNT: TourStep = { element: ".rvbar .cnt", title: "Where you've got to", text: "This counts what's left. Previous and Next jump between open items." };
const SEND: TourStep = { element: ".rvbar .send-btn", title: "Send it back", text: "When you're ready, this sends your answers to the agent. What you sent locks until it replies, and everything else stays open." };
const COPY: TourStep = { element: ".rvbar-r2 > .copy", title: "Copy results", text: "This copies your answers as text, to paste wherever you need them." };
const MORE: TourStep = { element: ".rvbar .more-btn", title: "More", text: "Mark every open item at once, see History, or save this round." };
const ITEM_MORE: TourStep = { element: ".item-more-btn", title: "More on an item", text: "Each item has its own actions here, such as generating an email." };
const BLOCKER: TourStep = { element: ".rvcard:not(.settled) .blocker-btn", title: "Something's stopping you?", text: "Blocker sends this one item to the agent straight away." };
const ID: TourStep = { element: ".rvhead .rid", title: "Item ids", text: "Every id is a link to its item, and Blocked by links the same way." };

/** The built-in tours, by page kind, with round phases as its own. custom/custom.js can add one by template name. */
export const tours: Record<string, TourStep[]> = {
  review: [ANSWER, ID, ITEM_MORE, BLOCKER, COUNT, SEND, COPY, MORE],
  checklist: [ANSWER, { element: ".howto-btn", title: "How to test", text: "This opens the test steps in their own window." },
    { element: ".st.blk", title: "Blocked by", text: "A blocked item waits for the one it names. The link goes there." }, BLOCKER, COUNT, SEND, MORE],
  journey: [ANSWER, { element: ".rvrestart", title: "Restart from a checkpoint", text: "Go back to a checkpoint you've reached. The steps up to it stay Yes." }, COUNT, SEND, MORE],
  backlog: [{ element: ".rvcard .seg", title: "Pick for each item", text: "Pick an option. An item you leave alone keeps its default." }, COUNT, SEND, MORE],
  questions: [{ element: ".qans", title: "Type your answer", text: "Each question takes free text. Use suggestion fills in the agent's guess." }, COUNT, SEND, MORE],
  round: [ANSWER, { element: '[data-v="risk"]', title: "Accept risk", text: "If you'll accept a risk, say how it's presented. That note is required." }, ITEM_MORE, COUNT, SEND, COPY, MORE],
  "round-phases": [{ element: ".phase", title: "Phases", text: "The work is split into lettered phases, each with its own goal." },
    { element: '[data-v="risk"]', title: "Accept risk", text: "A phase closes when each step is Yes or Accept risk. Accept risk needs a note." },
    { element: ".phase-send", title: "Send a phase", text: "Each phase goes on its own, so one can go before the others." },
    { element: ".phase .st.blk", title: "Blocked by", text: "A phase can wait on another phase or on a single step." },
    ITEM_MORE, COUNT, { ...MORE, text: "Build a deck is here. It asks what you're building, then sends only the final Yes and Accept risk items to the agent." }],
  reference: [{ element: ".info", title: "Nothing to answer", text: "This page is for reading. It updates by itself when the agent changes it." }],
  status: [{ element: ".info", title: "Nothing to answer", text: "This page is for reading. It updates by itself when the agent changes it." }],
};

const seenKey = (key: string) => "handoff-tour-seen:" + key;

export function tourSeen(key: string): boolean {
  try { return localStorage.getItem(seenKey(key)) === "1"; } catch { return false; }
}

function markSeen(key: string): void {
  try { localStorage.setItem(seenKey(key), "1"); } catch { /* a private window just offers it again */ }
}

function addStyle(): void {
  if (document.getElementById("tour-css")) return;
  const s = document.createElement("style"); s.id = "tour-css"; s.textContent = css; document.head.prepend(s);
}

const visible = (selector: string) => { const el = document.querySelector(selector); return !!el && el.getClientRects().length > 0; };

/** Runs a tour over what's on this page. It's only ever started by the person. */
export function startTour(key: string, onDone: () => void): void {
  addStyle();
  const steps = (tours[key] ?? []).filter(s => visible(s.element));
  if (!steps.length) return;
  const tour = driver({
    showProgress: true, nextBtnText: "Next", prevBtnText: "Back", doneBtnText: "Done",
    steps: steps.map(s => ({ element: s.element, popover: { title: s.title, description: s.text } })),
    onDestroyStarted: () => { markSeen(key); onDone(); tour.destroy(); },
  });
  tour.drive();
}
