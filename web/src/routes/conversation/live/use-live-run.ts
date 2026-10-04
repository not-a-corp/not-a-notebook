import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import type { ConversationDetail } from "@/api/conversation-detail";
import { followRun, type Connection } from "@/api/runs";

import { applyEvent, newLiveRun, type LiveRun } from "./live-run";

export function conversationKey(id: string) {
  return ["conversation", id];
}

export interface LiveState {
  live: LiveRun | null;
  connection: Connection;
}

// One live run per conversation (design.md §4): whenever the conversation has
// an active run — one this tab started, or one already going when the page
// opened — follow its stream, and apply each event to the cached conversation
// and to the live state. The stream replays from the first event, which the
// reducer lands in the same place.
export function useLiveRun(conversationId: string, activeRunId: string | null): LiveState {
  const queryClient = useQueryClient();
  const [live, setLive] = useState<LiveRun | null>(null);
  const [connection, setConnection] = useState<Connection>("live");
  const liveRef = useRef<LiveRun | null>(null);

  useEffect(() => {
    if (activeRunId === null) {
      return;
    }

    const key = conversationKey(conversationId);
    const controller = new AbortController();
    liveRef.current = newLiveRun(activeRunId);
    setLive(liveRef.current);
    setConnection("live");
    // The sidebar marks a conversation with a run in progress.
    void queryClient.invalidateQueries({ queryKey: ["conversations"] });

    void followRun(
      activeRunId,
      {
        onEvent: (event) => {
          const detail = queryClient.getQueryData<ConversationDetail>(key);
          if (detail === undefined) {
            return;
          }

          const next = applyEvent(
            { detail, live: liveRef.current },
            event,
            new Date().toISOString(),
          );
          liveRef.current = next.live;
          setLive(next.live);
          queryClient.setQueryData(key, next.detail);

          if (event.type === "run.finished") {
            // What the stream does not carry — the kernel's state, a cell's
            // executed_at — comes from one fresh read of the conversation.
            void queryClient.invalidateQueries({ queryKey: key });
            void queryClient.invalidateQueries({ queryKey: ["conversations"] });
          }
        },
        onConnection: setConnection,
      },
      controller.signal,
    );

    return () => {
      controller.abort();
    };
  }, [activeRunId, conversationId, queryClient]);

  return { live, connection };
}
