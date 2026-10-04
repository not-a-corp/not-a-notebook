import type { RestartReason } from "@/api/events";

// Why the kernel restarted, in the words of design.md §3.7. The idle timeout is
// the instance's setting, which the API does not report, so it is not named.
export function restartReason(reason: RestartReason): string {
  switch (reason) {
    case "idle":
      return "idle";
    case "died":
      return "it stopped — out of memory, most often";
    case "requested":
      return "you restarted it";
    case "run_all":
      return "Run all starts from nothing";
    case "lost":
      return "the server restarted";
  }
}
