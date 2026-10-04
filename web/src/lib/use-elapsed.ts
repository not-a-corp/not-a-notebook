import { useEffect, useState } from "react";

// Milliseconds since `since`, ticking while it is set.
export function useElapsed(since: string | null): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (since === null) {
      return;
    }
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 100);
    return () => {
      clearInterval(timer);
    };
  }, [since]);

  if (since === null) {
    return 0;
  }
  return Math.max(0, now - new Date(since).getTime());
}
