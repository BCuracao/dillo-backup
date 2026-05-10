"use client";

import Sidebar from "./Sidebar";
import { useDashboardHeartbeat } from "@/hooks/useDashboardHeartbeat";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  // Single heartbeat for the whole app — every page that uses this layout
  // marks the dashboard as "visible" so the tray suppresses OS toasts.
  useDashboardHeartbeat();

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        {children}
      </main>
    </div>
  );
}
