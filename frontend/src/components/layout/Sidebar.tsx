import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import {
  Users,
  Clock,
  Calendar,
  LogOut,
  LayoutDashboard,
  WalletCards,
  Receipt,
  CreditCard,
  ShieldCheck,
} from 'lucide-react';
import { AvatarWithBadge } from '../Avatar';
import { useAuth } from '@/contexts/AuthContext';
import dayflowLogo from '../../assets/dayflow-logo.png';

export const Sidebar: React.FC = () => {
  const { user, logout, isOwner } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.role === 'ADMIN' || user?.role === 'HR';
  const displayName =
    [user?.first_name, user?.last_name].filter(Boolean).join(' ') ||
    user?.login_id ||
    'User';
  const roleLabel =
    user?.role === 'HR'
      ? 'HR'
      : user?.role === 'ADMIN'
        ? 'Admin'
        : user?.role === 'INT'
          ? 'Intern'
          : 'Employee';

  const handleLogout = async () => {
    // Awaited so the refresh token is blacklisted server-side before we navigate.
    // Logout used to only clear localStorage, leaving the session valid for up to
    // a week (audit V-23).
    await logout();
    navigate('/login');
  };

  const getAttendanceLink = () => {
    return isAdmin ? '/attendance/admin' : '/attendance/employee';
  };

  const getLeavesLink = () => {
    return isAdmin ? '/leaves/admin' : '/leaves/employee';
  };

  const getProfileLink = () => {
    return isAdmin ? '/profile/admin' : '/profile/employee';
  };

  const getEmployeesLink = () => {
    return user?.role === 'ADMIN' ? '/employees/admin' : '/employees';
  };

  const navItems = [
    {
      to: isAdmin ? '/dashboard/admin' : '/dashboard/employee',
      icon: LayoutDashboard,
      label: 'Dashboard',
    },
    ...(isAdmin ? [{ to: getEmployeesLink(), icon: Users, label: 'Employees' }] : []),
    { to: getAttendanceLink(), icon: Clock, label: 'Attendance' },
    { to: getLeavesLink(), icon: Calendar, label: 'Leaves' },
    ...(isAdmin ? [{ to: '/payroll', icon: WalletCards, label: 'Payroll' }] : []),
    { to: '/expenses', icon: Receipt, label: 'Expenses' },
    // Billing and the audit trail are owner-only, server-side as well as here.
    ...(isOwner
      ? [
          { to: '/billing', icon: CreditCard, label: 'Billing' },
          { to: '/audit', icon: ShieldCheck, label: 'Audit trail' },
        ]
      : []),
  ];

  return (
    <aside className="fixed left-0 top-0 h-screen w-64 bg-sidebar flex flex-col z-50">
      {/* Logo */}
      <div className="p-6 flex items-center gap-3">
        <img 
          src={dayflowLogo} 
          alt="Dayflow" 
          className="h-10 w-auto max-w-[160px] object-contain"
        />
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-2">
        {navItems.map((item) => {
          let to = item.to;
          if (item.to === '/attendance') to = getAttendanceLink();
          if (item.to === '/leaves') to = getLeavesLink();

          return (
            <NavLink
              key={item.to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl transition-all duration-200 ${
                  isActive
                    ? 'bg-sidebar-primary text-sidebar-primary-foreground'
                    : 'text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                }`
              }
            >
              <item.icon size={20} />
              <span className="font-medium">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* User Profile Section */}
      <div className="p-4 border-t border-sidebar-border">
        <div 
          className="flex items-center gap-3 p-3 rounded-xl hover:bg-sidebar-accent transition-colors cursor-pointer"
          onClick={() => navigate(getProfileLink())}
        >
          <AvatarWithBadge
            name={displayName}
            role={isAdmin ? 'admin' : 'employee'}
            size="md"
          />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-sidebar-foreground truncate">
              {displayName}
            </p>
            <p className="text-xs text-sidebar-foreground/60">
              {roleLabel}
            </p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="w-full mt-2 flex items-center gap-3 px-4 py-2.5 rounded-xl text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
        >
          <LogOut size={18} />
          <span className="text-sm font-medium">Logout</span>
        </button>
      </div>
    </aside>
  );
};

export default Sidebar;
