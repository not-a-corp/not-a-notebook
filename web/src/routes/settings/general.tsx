import { Info } from "lucide-react";

import { cn } from "@/lib/cn";
import type { ThemeChoice } from "@/lib/theme";
import { useThemeChoice } from "@/lib/use-theme-choice";

import { Group, Row, SectionTitle } from "./settings-ui";

// A miniature of the screen in each theme. These are the one place colours are
// written outside the tokens: each card shows a theme other than the one in
// effect, so it cannot read them from the page (values from design.md §5.3).
interface Miniature {
  bg: string;
  surface: string;
  border: string;
  navDot: string;
  navFaint: string;
  title: string;
  line: string;
  keyword: string;
  accent: string;
  button: string;
}

const LIGHT: Miniature = {
  bg: "#ffffff",
  surface: "#f7f7f8",
  border: "#e4e4e7",
  navDot: "#6b6b74",
  navFaint: "#c4c4ca",
  title: "#18181b",
  line: "#a1a1aa",
  keyword: "#6d28d9",
  accent: "#0e7490",
  button: "#0e7490",
};

const DARK: Miniature = {
  bg: "#0b0d10",
  surface: "#121418",
  border: "#26292f",
  navDot: "#9a9aa3",
  navFaint: "#3a3d44",
  title: "#e7e7ea",
  line: "#5f6169",
  keyword: "#c4b5fd",
  accent: "#22b8cf",
  button: "#22b8cf",
};

const MOCHA: Miniature = {
  bg: "#1e1e2e",
  surface: "#181825",
  border: "#313244",
  navDot: "#a6adc8",
  navFaint: "#45475a",
  title: "#cdd6f4",
  line: "#6c7086",
  keyword: "#cba6f7",
  accent: "#89b4fa",
  button: "#cba6f7",
};

function Screen({ colors, clip }: { colors: Miniature; clip?: boolean }) {
  return (
    <div
      className="absolute inset-0"
      style={{
        background: colors.bg,
        clipPath: clip === true ? "inset(0 0 0 50%)" : undefined,
      }}
    >
      <div
        className="absolute inset-y-0 left-0 w-6"
        style={{ background: colors.surface, borderRight: `1px solid ${colors.border}` }}
      />
      <div
        className="absolute top-2.5 left-1.5 h-[3px] w-3 rounded-xs"
        style={{ background: colors.navDot }}
      />
      <div
        className="absolute top-[18px] left-1.5 h-[3px] w-2.5 rounded-xs"
        style={{ background: colors.navFaint }}
      />
      <div
        className="absolute top-2.5 left-8 h-1 w-11 rounded-xs"
        style={{ background: colors.title }}
      />
      <div
        className="absolute top-5 left-8 h-[3px] w-16 rounded-xs"
        style={{ background: colors.line }}
      />
      <div
        className="absolute top-8 right-2 left-8 h-[26px] rounded-sm"
        style={{ background: colors.surface, border: `1px solid ${colors.border}` }}
      />
      <div
        className="absolute top-[39px] left-[38px] h-[3px] w-[30px] rounded-xs"
        style={{ background: colors.keyword }}
      />
      <div
        className="absolute top-[47px] left-[38px] h-[3px] w-[46px] rounded-xs"
        style={{ background: colors.accent }}
      />
      <div
        className="absolute right-2 bottom-2 h-2 w-5 rounded-xs"
        style={{ background: colors.button }}
      />
    </div>
  );
}

const CARDS: { choice: ThemeChoice; label: string }[] = [
  { choice: "system", label: "System" },
  { choice: "light", label: "Light" },
  { choice: "dark", label: "Dark" },
  { choice: "mocha", label: "Catppuccin Mocha" },
];

function Preview({ choice }: { choice: ThemeChoice }) {
  switch (choice) {
    case "system":
      return (
        <>
          <Screen colors={LIGHT} />
          <Screen colors={DARK} clip />
        </>
      );
    case "light":
      return <Screen colors={LIGHT} />;
    case "dark":
      return <Screen colors={DARK} />;
    case "mocha":
      return <Screen colors={MOCHA} />;
  }
}

// design.md §2.6 — General: how the app looks in this browser.
export function GeneralSettings() {
  const [choice, choose] = useThemeChoice();

  return (
    <>
      <SectionTitle title="General" description="How not-a-notebook looks in this browser." />
      <Group label="Appearance">
        <Row
          label="Theme"
          help="Saved in this browser, not in your account. System follows your operating system's light or dark setting."
        >
          <div className="flex flex-col gap-3">
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-4 gap-3">
              {CARDS.map((card) => {
                const selected = choice === card.choice;
                return (
                  <button
                    key={card.choice}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    className="flex flex-col gap-2 text-left"
                    onClick={() => {
                      choose(card.choice);
                    }}
                  >
                    <span className="relative block h-20 w-full">
                      <span className="absolute inset-0 overflow-hidden rounded-lg border border-border">
                        <Preview choice={card.choice} />
                      </span>
                      {selected && (
                        <span className="absolute -inset-[3px] rounded-[10px] border-2 border-accent" />
                      )}
                    </span>
                    <span className="flex items-center gap-2 text-sm font-medium whitespace-nowrap">
                      <span
                        className={cn(
                          "size-3.5 flex-none rounded-full",
                          selected && "border-4 border-accent",
                          !selected && "border border-text/35",
                        )}
                      />
                      {card.label}
                    </span>
                  </button>
                );
              })}
            </div>
            <p className="flex items-start gap-2 text-xs text-text-muted">
              <Info className="size-3.5 flex-none" />
              <span className="text-pretty">
                Catppuccin Mocha's chart colours are close in lightness, so charts with five or more
                series are harder to tell apart with colour blindness.
              </span>
            </p>
          </div>
        </Row>
      </Group>
    </>
  );
}
