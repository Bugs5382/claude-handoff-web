import { useLayoutEffect, useRef, type ReactNode } from "react";

export interface FooterProps {
  /** The bar's look: all-done, approved, has-blocker, save-bad. */
  flags: string;
  status: ReactNode;
  saved: string;
  savedBad: boolean;
  /** The delivery line, in the first row when the bar splits. */
  delivery?: ReactNode;
  /** Pop-ups that open upward from the bar. */
  pops: ReactNode;
  jump: ReactNode;
  /** Send, then Copy results, Clear my answers and the rest. */
  children: ReactNode;
  /** Set when the second row always shows, such as with a deck button. */
  alwaysTwo?: boolean;
}

/** The bottom bar: one row when everything fits, two when it doesn't, and always two on a phone. */
export function Footer({ flags, status, saved, savedBad, delivery, pops, jump, children, alwaysTwo }: FooterProps) {
  const bar = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = bar.current as HTMLDivElement;
    const fit = () => {
      const cut = (x: Element | null) => !!x && x.scrollWidth > x.clientWidth + 1;
      el.classList.remove("two");
      if (alwaysTwo || matchMedia("(max-width: 480px)").matches || cut(el.querySelector(".rvbar-in")) || cut(el.querySelector(".cnt")) || cut(el.querySelector(".dlv-t"))) el.classList.add("two");
    };
    fit();
    addEventListener("resize", fit);
    void document.fonts?.ready.then(fit);
    return () => removeEventListener("resize", fit);
  });
  return (
    <div ref={bar} className={"rvbar " + flags} role="region" aria-label="Review progress">
      <div className="rvbar-in">{pops}
        <div className="rvbar-r1">{jump}{status}{delivery}
          <span className={"svst" + (savedBad ? " bad" : "")} aria-live="polite">{saved}</span>
        </div>
        <div className="rvbar-r2">{children}</div>
      </div>
    </div>
  );
}
