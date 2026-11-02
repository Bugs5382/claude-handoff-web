import { useState } from "react";
import { startTour, tourSeen, tours } from "@/lib/tour";

export interface TourButtonProps {
  /** The tour's name: a custom template's, else the page kind, or round-phases. */
  tour: string;
}

/** Starts the page's guided tour. Once it's been seen it offers to show it again. */
export function TourButton({ tour }: TourButtonProps) {
  const [seen, setSeen] = useState(() => tourSeen(tour));
  if (!tours[tour]?.length) return null;
  return <button type="button" className="tour-btn" onClick={() => startTour(tour, () => setSeen(true))}>{seen ? "See the tour again" : "Take the tour"}</button>;
}
