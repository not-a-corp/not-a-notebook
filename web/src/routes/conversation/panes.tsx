import { GripVertical, Maximize2, Minimize2, type LucideIcon } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";

import { clampShare, DEFAULT_CHAT_SHARE, type PaneLayout, type PaneName } from "./pane-layout";

// design.md §2.1 — the two panes, each under a 36 px tab strip: swapped by
// dragging a tab (or from the keyboard), resized from the divider, maximised
// from the strip.

export interface PaneContent {
  name: PaneName;
  icon: LucideIcon;
  label: string;
  detail?: string;
  children: ReactNode;
  // The pane's element, for what renders inside it from elsewhere (the drawer).
  onElement?: (element: HTMLElement | null) => void;
}

interface Drag {
  pane: PaneName;
  x: number;
  y: number;
  // Past the few pixels that tell a drag from a click.
  moving: boolean;
  overTarget: boolean;
}

const DRAG_THRESHOLD_PX = 4;

export function SplitPanes({
  layout,
  chat,
  notebook,
}: {
  layout: PaneLayout;
  chat: PaneContent;
  notebook: PaneContent;
}) {
  const container = useRef<HTMLDivElement>(null);
  const panes = useRef<Record<PaneName, HTMLElement | null>>({ chat: null, notebook: null });
  const [drag, setDrag] = useState<Drag | null>(null);
  const [resizing, setResizing] = useState(false);

  // While a tab is dragged: follow the pointer, find the pane under it, swap
  // on release over the other one; Escape cancels.
  const dragging = drag !== null;
  const draggedPane = drag?.pane ?? null;
  useEffect(() => {
    if (!dragging || draggedPane === null) {
      return;
    }
    const pane: PaneName = draggedPane;
    const start = { x: 0, y: 0, set: false };

    function overOther(x: number, y: number): boolean {
      let other: PaneName = "chat";
      if (pane === "chat") {
        other = "notebook";
      }
      const rect = panes.current[other]?.getBoundingClientRect();
      if (rect === undefined) {
        return false;
      }
      return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
    }

    function onMove(event: PointerEvent) {
      if (!start.set) {
        start.x = event.clientX;
        start.y = event.clientY;
        start.set = true;
      }
      const distance = Math.hypot(event.clientX - start.x, event.clientY - start.y);
      setDrag((current) => {
        if (current === null) {
          return current;
        }
        return {
          pane: current.pane,
          x: event.clientX,
          y: event.clientY,
          moving: current.moving || distance > DRAG_THRESHOLD_PX,
          overTarget: overOther(event.clientX, event.clientY),
        };
      });
    }

    function onUp(event: PointerEvent) {
      setDrag((current) => {
        if (current?.moving === true && overOther(event.clientX, event.clientY)) {
          layout.swap();
        }
        return null;
      });
    }

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDrag(null);
      }
    }

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("keydown", onKey);
    };
  }, [dragging, draggedPane, layout]);

  function startDrag(pane: PaneName, event: ReactPointerEvent) {
    if (event.button !== 0) {
      return;
    }
    setDrag({ pane, x: event.clientX, y: event.clientY, moving: false, overTarget: false });
  }

  function onDividerDown(event: ReactPointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    setResizing(true);
  }

  function onDividerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const box = container.current?.getBoundingClientRect();
    if (!resizing || box === undefined) {
      return;
    }
    let share = (event.clientX - box.left) / box.width;
    if (layout.chatSide === "right") {
      share = 1 - share;
    }
    layout.resize(clampShare(share, box.width));
  }

  const ordered = [chat, notebook];
  if (layout.chatSide === "right") {
    ordered.reverse();
  }
  // Clamped when it was set (onDividerMove); a narrower window is held by each
  // pane's minimum width.
  const share = layout.chatShare;

  return (
    <div
      ref={container}
      className={cn("relative flex min-h-0 flex-1", resizing && "cursor-col-resize select-none")}
    >
      {ordered.map((content, index) => {
        const hidden = layout.maximized !== null && layout.maximized !== content.name;
        const isChat = content.name === "chat";
        const dragged = drag?.moving === true && drag.pane === content.name;
        const target = drag?.moving === true && drag.pane !== content.name && drag.overTarget;

        return (
          <PaneFrame
            key={content.name}
            content={content}
            hidden={hidden}
            // The chat holds its share; the notebook takes the rest.
            style={chatWidth(isChat && layout.maximized === null, share)}
            maximized={layout.maximized === content.name}
            dragged={dragged}
            target={target}
            divider={index === 0 && layout.maximized === null}
            onTabPointerDown={(event) => {
              startDrag(content.name, event);
            }}
            onMaximize={() => {
              layout.toggleMaximized(content.name);
            }}
            setElement={(element) => {
              panes.current[content.name] = element;
            }}
            dividerHandlers={{
              onPointerDown: onDividerDown,
              onPointerMove: onDividerMove,
              onPointerUp: () => {
                setResizing(false);
              },
              onDoubleClick: () => {
                layout.resize(DEFAULT_CHAT_SHARE);
              },
            }}
            resizing={resizing}
          />
        );
      })}

      {drag?.moving === true && (
        <DraggedTab drag={drag} content={drag.pane === "chat" ? chat : notebook} />
      )}
    </div>
  );
}

function chatWidth(sized: boolean, share: number): { width: string } | undefined {
  if (!sized) {
    return undefined;
  }
  return { width: `${String(share * 100)}%` };
}

interface DividerHandlers {
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onPointerMove: (event: ReactPointerEvent<HTMLDivElement>) => void;
  onPointerUp: () => void;
  onDoubleClick: () => void;
}

function PaneFrame({
  content,
  hidden,
  style,
  maximized,
  dragged,
  target,
  divider,
  resizing,
  onTabPointerDown,
  onMaximize,
  setElement,
  dividerHandlers,
}: {
  content: PaneContent;
  hidden: boolean;
  style: { width: string } | undefined;
  maximized: boolean;
  dragged: boolean;
  target: boolean;
  divider: boolean;
  resizing: boolean;
  onTabPointerDown: (event: ReactPointerEvent) => void;
  onMaximize: () => void;
  setElement: (element: HTMLElement | null) => void;
  dividerHandlers: DividerHandlers;
}) {
  const Icon = content.icon;
  let maximizeLabel = `Maximise ${content.label.toLowerCase()}`;
  let MaximizeIcon = Maximize2;
  if (maximized) {
    maximizeLabel = `Restore ${content.label.toLowerCase()}`;
    MaximizeIcon = Minimize2;
  }

  function attach(element: HTMLElement | null) {
    setElement(element);
    content.onElement?.(element);
  }

  return (
    <>
      <section
        ref={attach}
        aria-label={content.label}
        style={style}
        className={cn(
          "relative flex min-w-[360px] flex-col",
          style === undefined && "flex-1",
          style !== undefined && "flex-none",
          hidden && "hidden",
        )}
      >
        <div className="flex h-9 flex-none items-stretch border-b border-border pr-1 pl-2">
          <Tooltip label="Drag to the other side to swap panes">
            <div
              role="button"
              tabIndex={-1}
              aria-label={`${content.label} pane`}
              className={cn(
                "flex cursor-grab items-center gap-2 px-3 text-sm font-medium whitespace-nowrap shadow-[inset_0_-2px_0_var(--text)] select-none",
                dragged &&
                  "my-1 rounded-md border border-dashed border-text/25 text-text-muted shadow-none",
              )}
              onPointerDown={onTabPointerDown}
            >
              <Icon className="size-3.5 text-text-muted" />
              {content.label}
              {content.detail !== undefined && (
                <span className="font-normal text-text-muted">· {content.detail}</span>
              )}
            </div>
          </Tooltip>
          <div className="flex-1" />
          <Tooltip label={maximizeLabel}>
            <Button
              variant="ghost"
              size="icon-compact"
              aria-label={maximizeLabel}
              className="self-center"
              onClick={onMaximize}
            >
              <MaximizeIcon className="size-3.5" />
            </Button>
          </Tooltip>
        </div>
        {content.children}
        {target && <DropTarget />}
      </section>
      {divider && <Divider handlers={dividerHandlers} active={resizing} />}
    </>
  );
}

// The pane a dragged tab would land on: tinted, edged, and saying so.
function DropTarget() {
  return (
    <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center bg-accent-soft/85 shadow-[inset_0_0_0_2px_var(--accent)]">
      <div className="flex h-8 items-center rounded-md border border-border bg-surface-raised px-3 text-sm font-medium">
        Drop to swap panes
      </div>
    </div>
  );
}

function DraggedTab({ drag, content }: { drag: Drag; content: PaneContent }) {
  const Icon = content.icon;
  return (
    <div
      className="pointer-events-none fixed z-50 flex h-9 items-center gap-2 rounded-md border border-border bg-surface-raised px-3 text-sm font-medium opacity-80 shadow-overlay"
      style={{ left: drag.x - 24, top: drag.y - 16 }}
    >
      <Icon className="size-3.5 text-text-muted" />
      {content.label}
    </div>
  );
}

// A 1 px line with an 8 px hit area; on hover it darkens and shows its grip
// (13 × 32); a double-click goes back to 40/60.
function Divider({ handlers, active }: { handlers: DividerHandlers; active: boolean }) {
  return (
    <div className="group/divider relative z-30 w-px flex-none bg-border">
      <Tooltip label="Drag to resize · double-click for 40/60" side="right">
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panes"
          className="absolute inset-y-0 -left-1 w-2 cursor-col-resize"
          onPointerDown={handlers.onPointerDown}
          onPointerMove={handlers.onPointerMove}
          onPointerUp={handlers.onPointerUp}
          onDoubleClick={handlers.onDoubleClick}
          // Here, not on pointerdown: it stops text being selected while
          // dragging without also stopping the browser's dblclick.
          onMouseDown={(event) => {
            event.preventDefault();
          }}
        />
      </Tooltip>
      <div
        className={cn(
          "pointer-events-none absolute inset-y-0 left-0 w-px bg-text-muted opacity-0 group-hover/divider:opacity-100",
          active && "opacity-100",
        )}
      />
      <div
        className={cn(
          "pointer-events-none absolute top-1/2 -left-1.5 flex h-8 w-[13px] -translate-y-1/2 items-center justify-center rounded-md border border-border bg-surface-raised text-text-muted opacity-0 group-hover/divider:opacity-100",
          active && "opacity-100",
        )}
      >
        <GripVertical className="size-3" />
      </div>
    </div>
  );
}
