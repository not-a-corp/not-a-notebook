import { useSyncExternalStore } from "react";

import { getSession, subscribeSession, type Session } from "./session";

export function useSession(): Session {
  return useSyncExternalStore(subscribeSession, getSession);
}
