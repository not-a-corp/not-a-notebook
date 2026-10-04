import { useEffect, useRef, type RefObject } from "react";

const NEAR_BOTTOM_PX = 48;

// A pane follows what is being added at its end — unless the person scrolled
// up to read, in which case it stays where they put it (design.md §2.5).
export function useStickToBottom(ref: RefObject<HTMLElement | null>, content: unknown): void {
  const pinned = useRef(true);

  useEffect(() => {
    const element = ref.current;
    if (element === null) {
      return;
    }
    function onScroll() {
      if (element === null) {
        return;
      }
      const distance = element.scrollHeight - element.scrollTop - element.clientHeight;
      pinned.current = distance < NEAR_BOTTOM_PX;
    }
    element.addEventListener("scroll", onScroll);
    return () => {
      element.removeEventListener("scroll", onScroll);
    };
  }, [ref]);

  useEffect(() => {
    const element = ref.current;
    if (element !== null && pinned.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [ref, content]);
}
