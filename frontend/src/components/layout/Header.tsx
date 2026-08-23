import React, { useEffect, useMemo, useState } from 'react';
import { AvatarWithBadge } from '../Avatar';
import { NotificationBell } from './NotificationBell';
import { useAuth } from '@/contexts/AuthContext';
import { useNavigate } from 'react-router-dom';
import {
  checkInAttendance,
  checkOutAttendance,
  fetchMyAttendance,
  type AttendanceRecord,
} from '@/api/attendance';
import { useToast } from '@/hooks/use-toast';
import { useRealtimeRefresh } from '@/hooks/useRealtimeRefresh';
import { fetchCompanyConfig } from '@/api/companyConfig';

interface HeaderProps {
  breadcrumb: string;
  subtitle?: string;
}

type AttendanceState = 'pending' | 'checked-in' | 'checked-out' | 'on-leave';

const toLocalDateString = (value: Date) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const formatTime = (value: string | null) => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

export const Header: React.FC<HeaderProps> = ({ breadcrumb, subtitle }) => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [bypassAttendance, setBypassAttendance] = useState(false);
  const [todayAttendance, setTodayAttendance] = useState<AttendanceRecord | null>(null);
  const [isAttendanceLoading, setIsAttendanceLoading] = useState(false);
  const [isAttendanceActionLoading, setIsAttendanceActionLoading] = useState(false);
  const isAdmin = user?.role === 'ADMIN' || user?.role === 'HR';
  const displayName =
    [user?.first_name, user?.last_name].filter(Boolean).join(' ') ||
    user?.login_id ||
    'User';

  const attendanceState = useMemo<AttendanceState>(() => {
    if (todayAttendance?.status === 'LEAVE') return 'on-leave';
    if (!todayAttendance?.check_in) return 'pending';
    if (!todayAttendance.check_out) return 'checked-in';
    return 'checked-out';
  }, [todayAttendance]);

  useEffect(() => {
    if (isAdmin) {
      setTodayAttendance(null);
      return;
    }

    let mounted = true;
    const loadTodayAttendance = async () => {
      setIsAttendanceLoading(true);
      try {
        const [records, config] = await Promise.all([
          fetchMyAttendance(),
          fetchCompanyConfig().catch(() => null)
        ]);
        if (!mounted) return;

        if (config) {
          setBypassAttendance(!!config.bypass_attendance);
        }

        const today = toLocalDateString(new Date());
        const todayRecord = records.find((record) => record.date === today) ?? null;
        setTodayAttendance(todayRecord);
      } catch (error) {
        if (mounted) {
          toast({
            title: 'Attendance unavailable',
            description: error instanceof Error ? error.message : 'Failed to load attendance state.',
            variant: 'destructive',
          });
        }
      } finally {
        if (mounted) {
          setIsAttendanceLoading(false);
        }
      }
    };

    loadTodayAttendance();
    return () => {
      mounted = false;
    };
  }, [isAdmin, toast]);

  useEffect(() => {
    if (isAdmin || isAttendanceLoading || attendanceState !== 'pending') return;
    const today = toLocalDateString(new Date());
    const reminderKey = `dayflow_checkin_reminder_${today}`;
    if (localStorage.getItem(reminderKey)) return;

    toast({
      title: 'Check-in pending',
      description: 'Please check in for today.',
    });
    localStorage.setItem(reminderKey, '1');
  }, [attendanceState, isAdmin, isAttendanceLoading, toast]);

  const refreshTodayAttendance = async () => {
    const records = await fetchMyAttendance();
    const today = toLocalDateString(new Date());
    const todayRecord = records.find((record) => record.date === today) ?? null;
    setTodayAttendance(todayRecord);
  };

  useRealtimeRefresh(() => {
    if (!isAdmin) {
      void refreshTodayAttendance();
    }
  });

  const handleAttendanceAction = async () => {
    if (isAttendanceActionLoading || isAttendanceLoading) return;
    if (attendanceState === 'checked-out' || attendanceState === 'on-leave') return;

    setIsAttendanceActionLoading(true);
    try {
      if (attendanceState === 'pending') {
        await checkInAttendance();
        toast({ title: 'Checked in', description: 'Your check-in time is recorded.' });
      } else {
        await checkOutAttendance();
        toast({ title: 'Checked out', description: 'Your check-out time is recorded.' });
      }
      await refreshTodayAttendance();
    } catch (error) {
      toast({
        title: 'Attendance update failed',
        description: error instanceof Error ? error.message : 'Please try again.',
        variant: 'destructive',
      });
    } finally {
      setIsAttendanceActionLoading(false);
    }
  };

  const getProfileLink = () => {
    return isAdmin ? '/profile/admin' : '/profile/employee';
  };

  return (
    <header className="sticky top-0 z-40 h-16 bg-card border-b border-border flex items-center justify-between px-6 shadow-soft">
      {/* Breadcrumb */}
      <div>
        <h1 className="text-lg font-semibold text-foreground">{breadcrumb}</h1>
        {subtitle && (
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>

      {/* Right Section */}
      <div className="flex items-center gap-4">
        {!isAdmin && (
          bypassAttendance ? (
            <div className="px-3 py-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-left select-none">
              <p className="text-xs font-semibold">Auto-Present Active</p>
              <p className="text-[10px] text-emerald-500/80">Attendance bypass enabled</p>
            </div>
          ) : (
            <button
              onClick={handleAttendanceAction}
              disabled={
                isAttendanceLoading ||
                isAttendanceActionLoading ||
                attendanceState === 'checked-out' ||
                attendanceState === 'on-leave'
              }
              className="px-3 py-1.5 rounded-lg border border-border bg-background text-left transition-transform hover:scale-105 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <p className="text-xs font-semibold text-foreground">
                {isAttendanceLoading
                  ? 'Loading...'
                  : attendanceState === 'on-leave'
                    ? 'On Leave'
                    : attendanceState === 'pending'
                    ? 'Check In'
                    : attendanceState === 'checked-in'
                      ? 'Check Out'
                      : 'Done'}
              </p>
              <p className="text-[11px] text-muted-foreground">
                {attendanceState === 'pending'
                  ? 'Pending'
                  : attendanceState === 'on-leave'
                    ? 'Approved leave for today'
                  : attendanceState === 'checked-in'
                    ? `Checked in at ${formatTime(todayAttendance?.check_in ?? null)}`
                    : `Checked out at ${formatTime(todayAttendance?.check_out ?? null)}`}
              </p>
            </button>
          )
        )}

        <NotificationBell />

        {/* User Avatar */}
        <button 
          onClick={() => navigate(getProfileLink())}
          className="transition-transform hover:scale-105"
        >
          <AvatarWithBadge
            name={displayName}
            role={isAdmin ? 'admin' : 'employee'}
            size="md"
          />
        </button>
      </div>
    </header>
  );
};

export default Header;
