import React from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { SubscriptionBanner } from "@/components/billing/SubscriptionBanner";

/**
 * Chrome only. Authentication and role checks live in `RequireAuth`, which wraps
 * this layout in App.tsx -- this component used to be the only guard in the app,
 * and it checked nothing but a localStorage flag (audit V-24).
 */
export const DashboardLayout: React.FC = () => (
  <div className="flex min-h-screen bg-background">
    <Sidebar />
    <main className="ml-64 flex-1">
      <SubscriptionBanner />
      <Outlet />
    </main>
  </div>
);

export default DashboardLayout;
