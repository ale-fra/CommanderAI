import { Group, Tooltip, UnstyledButton } from "@mantine/core";
import { COLOR_NAMES, toggleColor, WUBRG } from "../lib/colors";
import classes from "./ColorPicker.module.css";

interface ColorPickerProps {
  value: string[];
  /** Called with the toggled color. Pages whose state lives in the URL apply the toggle to
   *  the latest URL themselves (two quick clicks must not lose the first). */
  onToggle?: (color: string) => void;
  /** Convenience for local state: the new selection. */
  onChange?: (value: string[]) => void;
  withColorless?: boolean;
  label?: string;
}

/** WUBRG (+ colorless) toggle buttons using mana symbols. */
export function ColorPicker({
  value,
  onToggle,
  onChange,
  withColorless = true,
  label = "Colors",
}: ColorPickerProps) {
  const options = withColorless ? [...WUBRG, "C"] : [...WUBRG];
  const toggle = (c: string) => {
    onToggle?.(c);
    onChange?.(toggleColor(value, c));
  };
  return (
    <Group gap={6} role="group" aria-label={label}>
      {options.map((c) => {
        const active = value.includes(c);
        return (
          <Tooltip key={c} label={COLOR_NAMES[c]} openDelay={400}>
            <UnstyledButton
              className={classes.button}
              data-active={active || undefined}
              aria-pressed={active}
              aria-label={COLOR_NAMES[c]}
              onClick={() => toggle(c)}
            >
              <i className={`ms ms-cost ms-${c.toLowerCase()}`} aria-hidden="true" />
            </UnstyledButton>
          </Tooltip>
        );
      })}
    </Group>
  );
}
