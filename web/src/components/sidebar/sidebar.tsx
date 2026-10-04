import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Ellipsis, LogOut, PanelLeft, Search, SquarePen, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { getAccount, logout } from "@/api/auth";
import { listConversations } from "@/api/conversations";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip } from "@/components/ui/tooltip";
import { Wordmark } from "@/components/wordmark";
import { cn } from "@/lib/cn";
import { readPreference, savePreference } from "@/lib/preferences";
import { useHotkey } from "@/lib/use-hotkey";

import { groupByActivity } from "./groups";

const ROW = "flex h-8 items-center gap-2 rounded-md px-2";
// The open conversation, and a hovered row: `text` at 8% (design.md §2.1).
const ROW_ACTIVE = "bg-text/8 font-medium";

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(value);
    }, ms);
    return () => {
      clearTimeout(timer);
    };
  }, [value, ms]);

  return debounced;
}

// design.md §2.1 — 248 px, collapsible to 56 px of icons.
export function Sidebar() {
  const [collapsed, setCollapsed] = useState(() => readPreference("sidebar") === "collapsed");

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    savePreference("sidebar", next ? "collapsed" : "open");
  }

  if (collapsed) {
    return <CollapsedSidebar onExpand={toggle} />;
  }

  return (
    <aside className="flex h-full w-[248px] flex-none flex-col border-r border-border bg-surface text-sm">
      <div className="flex h-12 flex-none items-center justify-between pr-2 pl-4">
        <Wordmark />
        <Tooltip label="Collapse sidebar">
          <Button variant="ghost" size="icon" aria-label="Collapse sidebar" onClick={toggle}>
            <PanelLeft className="size-4" />
          </Button>
        </Tooltip>
      </div>
      <ConversationList />
      <AccountRow collapsed={false} />
    </aside>
  );
}

function CollapsedSidebar({ onExpand }: { onExpand: () => void }) {
  return (
    <aside className="flex h-full w-14 flex-none flex-col items-center gap-1 border-r border-border bg-surface py-2">
      <Tooltip label="Expand sidebar" side="right">
        <Button variant="ghost" size="icon" aria-label="Expand sidebar" onClick={onExpand}>
          <PanelLeft className="size-4" />
        </Button>
      </Tooltip>
      <Tooltip label="New conversation" side="right">
        <Link
          to="/"
          aria-label="New conversation"
          className={cn(ROW, "size-8 justify-center px-0")}
        >
          <SquarePen className="size-4" />
        </Link>
      </Tooltip>
      <div className="flex-1" />
      <AccountRow collapsed />
    </aside>
  );
}

function ConversationList() {
  const [searching, setSearching] = useState(false);
  const [search, setSearch] = useState("");
  const query = useDebounced(search.trim(), 200);
  const inputRef = useRef<HTMLInputElement>(null);

  useHotkey({ key: "k", mod: true }, () => {
    setSearching(true);
    inputRef.current?.focus();
  });

  useEffect(() => {
    if (searching) {
      inputRef.current?.focus();
    }
  }, [searching]);

  function stopSearching() {
    setSearch("");
    setSearching(false);
  }

  const conversations = useInfiniteQuery({
    queryKey: ["conversations", query],
    queryFn: ({ pageParam }) => listConversations(pageParam, query),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      if (last.page >= last.pages) {
        return undefined;
      }
      return last.page + 1;
    },
  });

  // Infinite scroll: the next page is fetched when the end of the list shows.
  const sentinelRef = useRef<HTMLDivElement>(null);
  const { hasNextPage, isFetchingNextPage, fetchNextPage } = conversations;
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (sentinel === null || !hasNextPage) {
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      const visible = entries.some((entry) => entry.isIntersecting);
      if (visible && !isFetchingNextPage) {
        void fetchNextPage();
      }
    });
    observer.observe(sentinel);
    return () => {
      observer.disconnect();
    };
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const all = conversations.data?.pages.flatMap((page) => page.data) ?? [];
  const groups = groupByActivity(all, new Date());

  let empty: ReactNode = null;
  if (conversations.isSuccess && all.length === 0) {
    let text = "No conversations yet.";
    if (query !== "") {
      text = "No conversation matches.";
    }
    empty = <p className="px-2 text-xs text-text-muted">{text}</p>;
  }

  return (
    <>
      <nav className="flex flex-col gap-0.5 px-2 pt-1 pb-3">
        <Link
          to="/"
          className={ROW}
          activeOptions={{ exact: true }}
          activeProps={{ className: ROW_ACTIVE }}
        >
          <SquarePen className="size-4" />
          <span className="flex-1 font-medium">New conversation</span>
        </Link>
        {searching && (
          <div className={cn(ROW, "bg-bg ring-1 ring-border")}>
            <Search className="size-4 text-text-muted" />
            <input
              ref={inputRef}
              value={search}
              placeholder="Search conversations"
              aria-label="Search conversations"
              className="min-w-0 flex-1 bg-transparent outline-none placeholder:text-text-muted"
              onChange={(event) => {
                setSearch(event.target.value);
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  stopSearching();
                }
              }}
            />
            <button
              type="button"
              aria-label="Stop searching"
              className="text-text-muted"
              onClick={stopSearching}
            >
              <X className="size-4" />
            </button>
          </div>
        )}
        {!searching && (
          <button
            type="button"
            className={cn(ROW, "text-text-muted hover:bg-text/8")}
            onClick={() => {
              setSearching(true);
            }}
          >
            <Search className="size-4" />
            <span className="flex-1 text-left">Search</span>
            <kbd className="rounded-sm border border-border px-1 font-mono text-xs">⌘K</kbd>
          </button>
        )}
      </nav>

      <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-2 pb-2">
        {empty}
        {groups.map((group) => (
          <section key={group.label} className="flex flex-col gap-0.5">
            <h2 className="px-2 pb-1 text-xs font-medium text-text-muted">{group.label}</h2>
            {group.conversations.map((conversation) => (
              <Link
                key={conversation.id}
                to="/c/$conversationId"
                params={{ conversationId: conversation.id }}
                className={cn(ROW, "hover:bg-text/8")}
                activeProps={{ className: ROW_ACTIVE }}
              >
                <span className="min-w-0 flex-1 truncate">{conversation.title}</span>
                {conversation.activeRunId !== null && (
                  <span
                    role="img"
                    aria-label="Running"
                    className="size-1.5 flex-none rounded-full bg-accent"
                  />
                )}
              </Link>
            ))}
          </section>
        ))}
        <div ref={sentinelRef} className="h-px flex-none" />
      </div>
    </>
  );
}

function AccountRow({ collapsed }: { collapsed: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const account = useQuery({ queryKey: ["account"], queryFn: getAccount });
  const email = account.data?.email ?? "";
  // The API keeps no name: the email's first letter stands in (design.md §2.1).
  const initial = email.charAt(0).toUpperCase();

  async function signOut() {
    await logout();
    queryClient.clear();
    await navigate({ to: "/login" });
  }

  const avatar = (
    <span className="flex size-6 flex-none items-center justify-center rounded-full bg-text/12 text-xs font-semibold">
      {initial}
    </span>
  );

  const menu = (
    <DropdownMenuContent side="top" align="start" className="w-56">
      <DropdownMenuItem
        onSelect={() => {
          void signOut();
        }}
      >
        <LogOut />
        Sign out
      </DropdownMenuItem>
    </DropdownMenuContent>
  );

  if (collapsed) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label="Account"
          className="flex size-10 items-center justify-center rounded-md hover:bg-text/8"
        >
          {avatar}
        </DropdownMenuTrigger>
        {menu}
      </DropdownMenu>
    );
  }

  return (
    <div className="flex flex-none flex-col gap-0.5 border-t border-border p-2">
      <DropdownMenu>
        <DropdownMenuTrigger className="flex h-10 items-center gap-2 rounded-md px-2 text-left hover:bg-text/8">
          {avatar}
          <span className="min-w-0 flex-1 truncate font-medium">{email}</span>
          <Ellipsis className="size-4 text-text-muted" />
        </DropdownMenuTrigger>
        {menu}
      </DropdownMenu>
    </div>
  );
}
