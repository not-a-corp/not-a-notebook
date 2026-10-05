import { Outlet } from "@tanstack/react-router";

import { Toaster } from "@/components/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";

export function Root() {
  return (
    <TooltipProvider delayDuration={400}>
      <Outlet />
      <Toaster />
    </TooltipProvider>
  );
}
