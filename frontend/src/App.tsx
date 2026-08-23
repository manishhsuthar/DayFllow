import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "@/contexts/AuthContext";
import { DashboardLayout } from "@/components/layout/DashboardLayout";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { RealtimeSync } from "@/components/RealtimeSync";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import ChangePassword from "./pages/ChangePassword";
import PlanSelection from "./pages/PlanSelection";
import Billing from "./pages/Billing";
import Employees from "./pages/Employees";
import EmployeesAdmin from "./pages/EmployeesAdmin";
import CreateEmployee from "./pages/CreateEmployee";
import AdminDashboard from "./pages/AdminDashboard";
import EmployeeDashboard from "./pages/EmployeeDashboard";
import AdminProfile from "./pages/AdminProfile";
import EmployeeProfile from "./pages/EmployeeProfile";
import AdminAttendance from "./pages/AdminAttendance";
import EmployeeAttendance from "./pages/EmployeeAttendance";
import AdminLeaves from "./pages/AdminLeaves";
import EmployeeLeaves from "./pages/EmployeeLeaves";
import CompanySetup from "./pages/CompanySetup";
import Payroll from "./pages/Payroll";
import Expenses from "./pages/Expenses";
import AuditLog from "./pages/AuditLog";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (failureCount, error: any) => {
        // Never retry an authorization or validation failure.
        if (error?.status && error.status >= 400 && error.status < 500) return false;
        return failureCount < 2;
      },
      staleTime: 30_000,
    },
  },
});

const App = () => (
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <HashRouter>
          <RealtimeSync />
          <Routes>
            {/* Public */}
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/plans" element={<PlanSelection />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />

            {/* Authenticated, but reachable while a password rotation is pending */}
            <Route path="/change-password" element={<ChangePassword />} />

            {/* Any authenticated role */}
            <Route element={<RequireAuth />}>
              <Route element={<DashboardLayout />}>
                <Route path="/dashboard/employee" element={<EmployeeDashboard />} />
                <Route path="/profile/employee" element={<EmployeeProfile />} />
                <Route path="/attendance/employee" element={<EmployeeAttendance />} />
                <Route path="/leaves/employee" element={<EmployeeLeaves />} />
                <Route path="/expenses" element={<Expenses />} />
              </Route>
            </Route>

            {/* ADMIN and HR */}
            <Route element={<RequireAuth roles={["ADMIN", "HR"]} />}>
              <Route element={<DashboardLayout />}>
                <Route path="/dashboard/admin" element={<AdminDashboard />} />
                <Route path="/employees" element={<Employees />} />
                <Route path="/employees/admin" element={<EmployeesAdmin />} />
                <Route path="/employees/new" element={<CreateEmployee />} />
                <Route path="/profile/admin" element={<AdminProfile />} />
                <Route path="/attendance/admin" element={<AdminAttendance />} />
                <Route path="/leaves/admin" element={<AdminLeaves />} />
                <Route path="/payroll" element={<Payroll />} />
              </Route>
            </Route>

            {/* ADMIN only: company settings, billing and the audit trail */}
            <Route element={<RequireAuth roles={["ADMIN"]} />}>
              <Route element={<DashboardLayout />}>
                <Route path="/billing" element={<Billing />} />
                <Route path="/audit" element={<AuditLog />} />
              </Route>
              <Route path="/company/setup" element={<CompanySetup />} />
            </Route>

            {/* Stripe Checkout returns here. */}
            <Route path="/billing/success" element={<Navigate to="/billing?checkout=success" replace />} />
            <Route path="/billing/cancelled" element={<Navigate to="/billing?checkout=cancelled" replace />} />

            <Route path="*" element={<NotFound />} />
          </Routes>
        </HashRouter>
      </TooltipProvider>
    </AuthProvider>
  </QueryClientProvider>
);

export default App;
