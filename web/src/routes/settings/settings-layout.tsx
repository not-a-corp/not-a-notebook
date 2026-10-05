import { Link, Outlet, useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { lastConversation } from "@/lib/last-conversation";
import { useHotkey } from "@/lib/use-hotkey";

const SECTIONS = [
  { to: "/settings/general", label: "General" },
  { to: "/settings/account", label: "Account" },
] as const;

// design.md §2.6 — a page of its own: a 48 px header with the way back, a
// 200 px nav, and the section at most 760 px wide.
export function SettingsLayout() {
  const navigate = useNavigate();

  function back() {
    const conversationId = lastConversation();
    if (conversationId === null) {
      void navigate({ to: "/" });
      return;
    }
    void navigate({ to: "/c/$conversationId", params: { conversationId } });
  }

  // Escape goes back — unless something open (a menu, a dialog) takes it first.
  useHotkey({ key: "Escape" }, (event) => {
    if (
      event.target instanceof HTMLElement &&
      event.target.closest("[role=dialog], [role=menu], [role=listbox], input, textarea")
    ) {
      return;
    }
    back();
  });

  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex h-12 flex-none items-center gap-2 border-b border-border pr-6 pl-3">
        <Tooltip label="Back to the conversation (Esc)">
          <Button variant="ghost" size="icon" aria-label="Back" onClick={back}>
            <ArrowLeft className="size-5" />
          </Button>
        </Tooltip>
        <span className="font-semibold">Settings</span>
      </header>
      <div className="flex min-h-0 flex-1">
        <nav className="flex w-[200px] flex-none flex-col gap-0.5 border-r border-border px-2 py-4 text-sm">
          {SECTIONS.map((section) => (
            <Link
              key={section.to}
              to={section.to}
              className="flex h-8 items-center rounded-md px-3 hover:bg-text/8"
              activeProps={{ className: "bg-text/8 font-medium" }}
            >
              {section.label}
            </Link>
          ))}
        </nav>
        <div className="min-w-0 flex-1 overflow-y-auto px-12 py-8">
          <div className="flex max-w-[760px] flex-col gap-8">
            <Outlet />
          </div>
        </div>
      </div>
    </div>
  );
}
