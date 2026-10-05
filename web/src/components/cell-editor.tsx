import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { HighlightStyle, indentUnit, syntaxHighlighting } from "@codemirror/language";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { useEffect, useRef } from "react";

import { SYNTAX_CLASSES } from "./syntax";

const highlight = HighlightStyle.define(SYNTAX_CLASSES);

// The editor wears the cell's box (design.md §2.5): no chrome of its own, the
// mono 13/20 of the read-only view, the caret and selection in the accent.
const look = EditorView.theme({
  "&": { backgroundColor: "transparent", fontSize: "13px" },
  "&.cm-focused": { outline: "none" },
  ".cm-content": {
    fontFamily: "var(--font-mono)",
    lineHeight: "20px",
    padding: "0",
    caretColor: "var(--accent)",
    fontVariantLigatures: "none",
  },
  ".cm-line": { padding: "0" },
  ".cm-cursor": { borderLeftColor: "var(--accent)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": {
    backgroundColor: "color-mix(in oklab, var(--accent) 22%, transparent) !important",
  },
});

export interface CellEditorProps {
  source: string;
  onChange: (source: string) => void;
  // Escape: leave the editor (§7).
  onLeave: () => void;
  // Ctrl/Cmd+Enter: run the cell and stay.
  onRun: () => void;
  // Shift+Enter: run the cell and move to the next.
  onRunAndNext: () => void;
}

export function CellEditor({ source, onChange, onLeave, onRun, onRunAndNext }: CellEditorProps) {
  const host = useRef<HTMLDivElement>(null);
  // The latest callbacks, read by the keymap the editor was built with once.
  const handlers = useRef({ onChange, onLeave, onRun, onRunAndNext });
  useEffect(() => {
    handlers.current = { onChange, onLeave, onRun, onRunAndNext };
  });
  const initial = useRef(source);

  useEffect(() => {
    const parent = host.current;
    if (parent === null) {
      return;
    }

    const cellKeys = keymap.of([
      {
        key: "Escape",
        run: () => {
          handlers.current.onLeave();
          return true;
        },
      },
      {
        key: "Shift-Enter",
        run: () => {
          handlers.current.onRunAndNext();
          return true;
        },
      },
      {
        key: "Mod-Enter",
        run: () => {
          handlers.current.onRun();
          return true;
        },
      },
    ]);

    const view = new EditorView({
      parent,
      state: EditorState.create({
        doc: initial.current,
        extensions: [
          cellKeys,
          history(),
          keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap]),
          indentUnit.of("    "),
          python(),
          syntaxHighlighting(highlight),
          look,
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              handlers.current.onChange(update.state.doc.toString());
            }
          }),
        ],
      }),
    });
    view.focus();
    // The caret goes to the end, where an edit usually continues.
    view.dispatch({ selection: { anchor: view.state.doc.length } });

    return () => {
      view.destroy();
    };
  }, []);

  return <div ref={host} className="min-h-5" />;
}
