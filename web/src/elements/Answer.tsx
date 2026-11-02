export interface AnswerOption { value: string; label: string }

export interface AnswerProps {
  /** The item's id, for the group's name. */
  id: string;
  options: AnswerOption[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

/** A segmented group of real buttons. Pressing the chosen one again clears it. */
export function Answer({ id, options, value, onChange, disabled }: AnswerProps) {
  return (
    <div className="seg" role="group" aria-label={"Answer for " + id}>
      {options.map(o => (
        <button key={o.value} type="button" data-v={o.value} data-label={o.label} aria-pressed={value === o.value} disabled={disabled}
          onClick={() => onChange(value === o.value ? "" : o.value)}>{o.label}</button>
      ))}
    </div>
  );
}
