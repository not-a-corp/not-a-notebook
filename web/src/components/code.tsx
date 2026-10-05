import { highlightCode, tagHighlighter } from "@lezer/highlight";
import { parser } from "@lezer/python";
import { useMemo, type ReactNode } from "react";

import { SYNTAX_CLASSES } from "./syntax";

// The same parser and colours the cell editor uses (./syntax.ts).
const highlighter = tagHighlighter(SYNTAX_CLASSES);

function highlighted(source: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let key = 0;

  highlightCode(
    source,
    parser.parse(source),
    highlighter,
    (text, classes) => {
      key += 1;
      if (classes === "") {
        nodes.push(text);
        return;
      }
      nodes.push(
        <span key={key} className={classes}>
          {text}
        </span>,
      );
    },
    () => {
      nodes.push("\n");
    },
  );

  return nodes;
}

export function PythonCode({ source }: { source: string }) {
  const nodes = useMemo(() => highlighted(source), [source]);
  return <code className="block font-mono text-sm whitespace-pre">{nodes}</code>;
}
