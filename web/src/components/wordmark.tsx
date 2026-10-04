// design.md §5.1: a 12 px square outlined in `text`, then the name in mono.
export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <span aria-hidden="true" className="size-3 rounded-[3px] border-2 border-text" />
      <span className="font-mono text-sm font-semibold tracking-[-0.2px]">not-a-notebook</span>
    </span>
  );
}
