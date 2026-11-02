import htm from "htm";
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { Answer } from "@/elements/Answer";
import { Blocks } from "@/elements/Blocks";
import { Button } from "@/elements/Button";
import { Chip } from "@/elements/Chip";
import { EmailDraft } from "@/elements/EmailDraft";
import { Footer } from "@/elements/Footer";
import { History } from "@/elements/History";
import { Item } from "@/elements/Item";
import { JumpBar, OpenIds } from "@/elements/JumpBar";
import { Page } from "@/elements/Page";
import { Phase } from "@/elements/Phase";
import { Restart } from "@/elements/Restart";
import { Round } from "@/elements/Round";
import { Thread } from "@/elements/Thread";

/** htm bound to React: custom templates use this with no compile step. */
export const html = htm.bind(createElement);
export { Answer, Blocks, Button, Chip, EmailDraft, Footer, History, Item, JumpBar, OpenIds, Page, Phase, Restart, Round, Thread };

const root = document.getElementById("app");
if (root) createRoot(root).render(createElement(Page));
