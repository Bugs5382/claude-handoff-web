import htm from "htm";
import { createElement } from "react";
import { createRoot } from "react-dom/client";
import { Answer } from "@/elements/Answer";
import { Blocks } from "@/elements/Blocks";
import { Button } from "@/elements/Button";
import { Chip } from "@/elements/Chip";
import { Choices } from "@/elements/Choices";
import { EmailDraft } from "@/elements/EmailDraft";
import { Footer } from "@/elements/Footer";
import { History } from "@/elements/History";
import { Item } from "@/elements/Item";
import { ItemMore } from "@/elements/ItemMore";
import { JumpBar, OpenIds } from "@/elements/JumpBar";
import { Page } from "@/elements/Page";
import { Phase } from "@/elements/Phase";
import { Restart } from "@/elements/Restart";
import { Round } from "@/elements/Round";
import { Thread } from "@/elements/Thread";
import { TourButton } from "@/elements/TourButton";
import { itemActions, loadCustom, pageActions, templates } from "@/lib/custom";
import { momentsFor } from "@/lib/moments";
import { tours } from "@/lib/tour";

/** htm bound to React: custom templates use this with no compile step. */
export const html = htm.bind(createElement);
export { itemActions, momentsFor, pageActions, templates, tours };
export { Answer, Blocks, Button, Chip, Choices, EmailDraft, Footer, History, Item, ItemMore, JumpBar, OpenIds, Page, Phase, Restart, Round, Thread, TourButton };

const root = document.getElementById("app");
// After this script finishes, so custom.js finds window.HandoffSite.
if (root) setTimeout(() => void loadCustom().then(() => createRoot(root).render(createElement(Page))));
