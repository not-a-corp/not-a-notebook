import { tags } from "@lezer/highlight";

// The syntax colours of design.md §5.3 as classes, so each theme's tokens apply.
// One list for the read-only view and the editor, so a cell reads the same in both.
export const SYNTAX_CLASSES = [
  { tag: [tags.keyword, tags.bool, tags.null, tags.self], class: "text-syntax-keyword" },
  { tag: [tags.string, tags.special(tags.string)], class: "text-syntax-string" },
  { tag: tags.number, class: "text-syntax-number" },
  {
    tag: [tags.function(tags.variableName), tags.function(tags.propertyName)],
    class: "text-syntax-function",
  },
  { tag: tags.comment, class: "text-syntax-comment" },
];
