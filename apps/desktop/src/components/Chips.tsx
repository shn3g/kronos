// SPDX-License-Identifier: AGPL-3.0-or-later

interface ChipOption<T extends string> {
  id: T;
  label: string;
}

interface ChipsProps<T extends string> {
  label: string;
  value: T;
  options: readonly ChipOption<T>[];
  onChange: (value: T) => void;
}

export function Chips<T extends string>({ label, value, options, onChange }: ChipsProps<T>) {
  return (
    <div className="chips" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          role="radio"
          aria-checked={option.id === value}
          className={option.id === value ? "chip chip--active" : "chip"}
          onClick={() => onChange(option.id)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
