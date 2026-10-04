import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // The stream keeps live data current; refetching on focus would only race it.
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});
