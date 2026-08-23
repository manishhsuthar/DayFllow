import React from 'react';
import { Header } from '@/components/layout/Header';
import { AvatarWithBadge } from '@/components/Avatar';
import { Mail, User, Briefcase, Building2, Calendar, Clock, Wallet } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/contexts/AuthContext';
import { fetchSalaryRecords } from '@/api/payroll';
import { formatAmount } from '@/api/billing';

const roleLabel = (role?: 'ADMIN' | 'HR' | 'EMP' | 'INT') => {
  if (role === 'ADMIN') return 'Admin';
  if (role === 'HR') return 'HR';
  if (role === 'INT') return 'Intern';
  if (role === 'EMP') return 'Employee';
  return '--';
};

const EmployeeProfile: React.FC = () => {
  const { user } = useAuth();
  const displayName =
    [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim() ||
    user?.login_id ||
    'User';
  const joiningDate = user?.date_of_joining
    ? new Date(`${user.date_of_joining}T00:00:00`).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    })
    : '--';
  // Salary is served by the payroll endpoint now, in USD. It used to live on the
  // user object and be handed to every colleague in the directory (audit V-18).
  const { data: salaryRecords } = useQuery({
    queryKey: ['my-salary'],
    queryFn: fetchSalaryRecords,
    retry: false,
  });
  const mySalary = salaryRecords?.[0];
  const formattedSalary = mySalary ? formatAmount(mySalary.monthly_salary) : '--';

  return (
    <div className="min-h-screen bg-background">
      <Header breadcrumb="Profile" subtitle="Employee Profile" />

      <div className="p-6">
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <div className="bg-card rounded-xl border border-border p-6">
              <div className="flex flex-col items-center text-center mb-6">
                <AvatarWithBadge name={displayName} role="employee" size="xl" />
                <h2 className="text-xl font-bold text-foreground mt-4">{displayName}</h2>
                <p className="text-primary font-medium">{roleLabel(user?.role)}</p>
              </div>

              <div className="space-y-4">
                <div className="flex items-center gap-3 text-sm">
                  <div className="p-2 bg-lavender rounded-lg">
                    <Briefcase size={16} className="text-primary" />
                  </div>
                  <span className="text-muted-foreground">Employee ID:</span>
                  <span className="text-foreground font-medium font-mono ml-auto">{user?.login_id || '--'}</span>
                </div>
                <div className="flex items-center gap-3 text-sm">
                  <div className="p-2 bg-lavender rounded-lg">
                    <Mail size={16} className="text-primary" />
                  </div>
                  <span className="text-foreground">{user?.email || '--'}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-2 space-y-6">
            <div className="bg-card rounded-xl border border-border p-6">
              <h3 className="font-semibold text-foreground mb-6">Basic Information</h3>
              <div className="grid md:grid-cols-2 gap-6">
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-lavender rounded-lg">
                    <User size={18} className="text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">First Name</p>
                    <p className="text-sm font-medium text-foreground">{user?.first_name || '--'}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-lavender rounded-lg">
                    <User size={18} className="text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Last Name</p>
                    <p className="text-sm font-medium text-foreground">{user?.last_name || '--'}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-lavender rounded-lg">
                    <Briefcase size={18} className="text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Role</p>
                    <p className="text-sm font-medium text-foreground">{roleLabel(user?.role)}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-lavender rounded-lg">
                    <Building2 size={18} className="text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Department</p>
                    <p className="text-sm font-medium text-foreground">{user?.department || '--'}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-lavender rounded-lg">
                    <Clock size={18} className="text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Employment Type</p>
                    <p className="text-sm font-medium text-foreground">{user?.employment_type || '--'}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-lavender rounded-lg">
                    <Calendar size={18} className="text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Date of Joining</p>
                    <p className="text-sm font-medium text-foreground">{joiningDate}</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="p-2 bg-lavender rounded-lg">
                    <Wallet size={18} className="text-primary" />
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Salary</p>
                    <p className="text-sm font-medium text-foreground">{formattedSalary}</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-card rounded-xl border border-border p-6">
              <h3 className="font-semibold text-foreground mb-2">Additional Profile Data</h3>
              <p className="text-sm text-muted-foreground">
                No extra profile details are available for this account yet.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmployeeProfile;
