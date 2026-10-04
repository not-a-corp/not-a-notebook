import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

// tailwind-merge has to know the design's type scale: without it `text-md`
// reads as a colour and is dropped beside `text-text-muted`.
const merge = extendTailwindMerge({
  extend: {
    theme: {
      text: ["xs", "sm", "base", "md", "lg", "xl"],
    },
  },
});

export function cn(...classes: ClassValue[]): string {
  return merge(clsx(classes));
}
