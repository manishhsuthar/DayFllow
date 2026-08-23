import React, { useEffect, useMemo, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { ChevronLeft, ChevronRight, Calendar, Check, Clock, ShieldCheck } from 'lucide-react';
import { fetchMyAttendance, type AttendanceRecord } from '@/api/attendance';
import { fetchCompanyConfig } from '@/api/companyConfig';
import { REALTIME_DATA_CHANGED_EVENT } from '@/hooks/useRealtimeUpdates';

const HOURS_PER_DAY = 8;

const parseDate = (value: string) => new Date(`${value}T00:00:00`);

const formatTime = (value: string | null) => {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
};

const formatHours = (hours: number) => {
  if (!Number.isFinite(hours)) return '--';
  return `${hours.toFixed(2)}h`;
};

const formatExtraHours = (hours: number) => {
  if (!Number.isFinite(hours)) return '--';
  const diff = hours - HOURS_PER_DAY;
  if (Math.abs(diff) < 0.01) return '0h 00m';

  const sign = diff > 0 ? '+' : '-';
  const totalMinutes = Math.round(Math.abs(diff) * 60);
  const displayHours = Math.floor(totalMinutes / 60);
  const displayMinutes = totalMinutes % 60;

  return `${sign}${displayHours}h ${String(displayMinutes).padStart(2, '0')}m`;
};

const EmployeeAttendance: React.FC = () => {
  const [currentDate, setCurrentDate] = useState(new Date());
  const [attendance, setAttendance] = useState<AttendanceRecord[]>([]);
  const [bypassAttendance, setBypassAttendance] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    const loadAttendance = async () => {
      try {
        const [data, config] = await Promise.all([
          fetchMyAttendance(),
          fetchCompanyConfig().catch(() => null)
        ]);
        if (isMounted) {
          if (config) {
            setBypassAttendance(!!config.bypass_attendance);
          }
          const sorted = [...data].sort((a, b) => b.date.localeCompare(a.date));
          setAttendance(sorted);
          setError(null);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load attendance.');
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadAttendance();
    const handleRealtimeRefresh = () => {
      loadAttendance();
    };
    window.addEventListener(REALTIME_DATA_CHANGED_EVENT, handleRealtimeRefresh);

    return () => {
      isMounted = false;
      window.removeEventListener(REALTIME_DATA_CHANGED_EVENT, handleRealtimeRefresh);
    };
  }, []);

  const monthAttendance = useMemo(() => {
    const month = currentDate.getMonth();
    const year = currentDate.getFullYear();

    return attendance.filter((record) => {
      const date = parseDate(record.date);
      return date.getMonth() === month && date.getFullYear() === year;
    });
  }, [attendance, currentDate]);

  const presentDays = useMemo(() => {
    if (bypassAttendance) {
      return new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0).getDate();
    }
    return monthAttendance.filter(
      (record) => record.status === 'PRESENT' || record.status === 'HALF_DAY',
    ).length;
  }, [bypassAttendance, monthAttendance, currentDate]);

  const leavesTaken = useMemo(() => {
    if (bypassAttendance) return 0;
    return monthAttendance.filter((record) => record.status === 'LEAVE').length;
  }, [bypassAttendance, monthAttendance]);

  const totalWorkingDays = useMemo(() => {
    if (bypassAttendance) {
      return new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0).getDate();
    }
    return monthAttendance.filter((record) => record.status !== 'LEAVE').length;
  }, [bypassAttendance, monthAttendance, currentDate]);

  const moveMonth = (offset: number) => {
    setCurrentDate((prev) => new Date(prev.getFullYear(), prev.getMonth() + offset, 1));
  };

  return (
    <div className="min-h-screen bg-background">
      <Header breadcrumb="Attendance" subtitle="For Employees" />
      <div className="p-6">
        <h2 className="text-2xl font-bold text-foreground mb-6">My Attendance</h2>
        <div className="bg-lavender rounded-xl p-6 mb-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <button onClick={() => moveMonth(-1)} className="p-2 hover:bg-card rounded-lg"><ChevronLeft size={18} /></button>
              <span className="font-medium text-foreground">{currentDate.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}</span>
              <button onClick={() => moveMonth(1)} className="p-2 hover:bg-card rounded-lg"><ChevronRight size={18} /></button>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-card rounded-xl p-4 text-center">
              <Check className="mx-auto mb-2 text-success-foreground" size={24} />
              <p className="text-2xl font-bold text-foreground">{isLoading ? '--' : presentDays}</p>
              <p className="text-sm text-muted-foreground">Days Present</p>
            </div>
            <div className="bg-card rounded-xl p-4 text-center">
              <Calendar className="mx-auto mb-2 text-info-foreground" size={24} />
              <p className="text-2xl font-bold text-foreground">{isLoading ? '--' : leavesTaken}</p>
              <p className="text-sm text-muted-foreground">Leaves Taken</p>
            </div>
            <div className="bg-card rounded-xl p-4 text-center">
              <Clock className="mx-auto mb-2 text-primary" size={24} />
              <p className="text-2xl font-bold text-foreground">{isLoading ? '--' : totalWorkingDays}</p>
              <p className="text-sm text-muted-foreground">Total Working Days</p>
            </div>
          </div>
        </div>
        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <table className="w-full">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Date</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Check In</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Check Out</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Work Hours</th>
                <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Extra Hours</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading ? (
                <tr>
                  <td className="px-4 py-10 text-center text-sm text-muted-foreground" colSpan={5}>
                    Loading attendance...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td className="px-4 py-10 text-center text-sm text-destructive" colSpan={5}>
                    {error}
                  </td>
                </tr>
              ) : bypassAttendance ? (
                <tr>
                  <td className="px-4 py-16 text-center text-sm" colSpan={5}>
                    <div className="flex flex-col items-center justify-center gap-2 text-emerald-600 dark:text-emerald-400">
                      <ShieldCheck size={40} className="stroke-[1.5]" />
                      <p className="font-semibold text-base mt-2">Attendance Bypass Enabled</p>
                      <p className="text-muted-foreground max-w-md text-xs">
                        Your company has enabled attendance bypass. You are automatically marked as present for all work days.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : monthAttendance.length === 0 ? (
                <tr>
                  <td className="px-4 py-10 text-center text-sm text-muted-foreground" colSpan={5}>
                    No attendance records for this month.
                  </td>
                </tr>
              ) : (
                monthAttendance.map((record) => {
                  const extraHours = record.total_hours - HOURS_PER_DAY;

                  return (
                    <tr key={record.id} className="hover:bg-muted/30">
                      <td className="px-4 py-3 text-sm text-foreground">{parseDate(record.date).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{formatTime(record.check_in)}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{formatTime(record.check_out)}</td>
                      <td className="px-4 py-3 text-sm text-foreground">{formatHours(record.total_hours)}</td>
                      <td className={`px-4 py-3 text-sm font-medium ${extraHours > 0 ? 'text-success-foreground' : 'text-muted-foreground'}`}>{formatExtraHours(record.total_hours)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default EmployeeAttendance;
