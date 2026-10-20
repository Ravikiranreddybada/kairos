import { Moon, Sun } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import { fetchModel } from "../api";
import { runLabel } from "../format";
import type { ModelCard } from "../types";

type Theme = "light" | "dark";

function currentTheme(): Theme {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function Masthead() {
  const [model, setModel] = useState<ModelCard | null>(null);
  const [down, setDown] = useState<string | null>(null);
  const [theme, setTheme] = useState<Theme>(currentTheme);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchModel(ctrl.signal)
      .then(setModel)
      .catch((e: Error) => e.name !== "AbortError" && setDown(e.message));
    return () => ctrl.abort();
  }, []);

  const flip = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("kairos.theme", next);
    } catch {
      // storage blocked: the choice lasts for this tab
    }
    setTheme(next);
  };

  const gates = model?.gates ?? [];
  const passed = gates.filter((g) => g.passed).length;

  return (
    <header className="flex items-center gap-4 border-b border-rule-strong bg-sheet px-4 sm:px-6">
      <span className="wordmark text-[19px] text-type">Kairos</span>
      <span className="hidden text-[13px] text-type-2 sm:inline">Planning copilot</span>

      <div className="ml-auto flex min-w-0 items-center gap-4 text-[12px]">
        {down ? (
          <span role="status" className="truncate text-errata">
            API unreachable
          </span>
        ) : model ? (
          <span className="hidden min-w-0 items-baseline gap-2 truncate text-type-2 md:flex" title={model.run_id}>
            Champion model
            <span className="num text-ink">{runLabel(model.run_id)}</span>
            {gates.length > 0 && (
              <span className="num text-type-2">
                {passed}/{gates.length} gates
              </span>
            )}
          </span>
        ) : (
          <span className="text-type-2">Connecting</span>
        )}
        <button
          type="button"
          onClick={flip}
          className="grid size-9 cursor-pointer place-items-center border border-rule-strong text-ink transition-colors
            duration-150 hover:bg-[var(--ink-wash)]"
          aria-label={theme === "dark" ? "Switch to paper (light) theme" : "Switch to carbon (dark) theme"}
        >
          {theme === "dark" ? <Sun size={18} weight="regular" /> : <Moon size={18} weight="regular" />}
        </button>
      </div>
    </header>
  );
}
