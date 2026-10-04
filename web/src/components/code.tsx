import { highlightCode, tagHighlighter, tags } from "@lezer/highlight";
import { parser } from "@lezer/python";
import { useMemo, type ReactNode } from "react";

// The syntax colours of design.md §5.3, by class, so each theme's tokens apply.
// The same parser the cell editor uses, so a cell reads the same in both.
const highlighter = tagHighlighter([
  { tag: [tags.keyword, tags.bool, tags.null, tags.self], class: "text-syntax-keyword" },
  { tag: [tags.string, tags.special(tags.string)], class: "text-syntax-string" },
  { tag: tags.number, class: "text-syntax-number" },
  {
    tag: [tags.function(tags.variableName), tags.function(tags.propertyName)],
    class: "text-syntax-function",
  },
  { tag: tags.comment, class: "text-syntax-comment" },
]);

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
