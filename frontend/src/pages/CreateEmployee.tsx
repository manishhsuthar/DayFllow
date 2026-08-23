import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Header } from '@/components/layout/Header';
import { createEmployee } from '@/api/employees';
import { fetchCompanyConfig } from '@/api/companyConfig';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/contexts/AuthContext';
import {
  REALTIME_DATA_CHANGED_EVENT,
  type RealtimeDataChangedEvent,
} from '@/hooks/useRealtimeUpdates';

const CreateEmployee: React.FC = () => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<'EMP' | 'INT' | 'HR'>('EMP');
  const [dateOfJoining, setDateOfJoining] = useState('');
  const [department, setDepartment] = useState('');
  const [employmentType, setEmploymentType] = useState('');
  const [salary, setSalary] = useState('');
  const [departmentOptions, setDepartmentOptions] = useState<string[]>([]);
  const [roleOptions, setRoleOptions] = useState<Array<'EMP' | 'INT' | 'HR'>>(['EMP', 'INT', 'HR']);
  const [employmentTypeOptions, setEmploymentTypeOptions] = useState<string[]>([]);
  const [isConfigLoading, setIsConfigLoading] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [created, setCreated] = useState<{ login_id: string; temporary_password: string } | null>(null);
  const navigate = useNavigate();
  const { toast } = useToast();
  const { user } = useAuth();
  const canCreateHr = user?.role === 'ADMIN';
  const employeesPagePath = user?.role === 'ADMIN' ? '/employees/admin' : '/employees';
  const hasConfigOptions = useMemo(
    () => departmentOptions.length > 0 && roleOptions.length > 0 && employmentTypeOptions.length > 0,
    [departmentOptions.length, roleOptions.length, employmentTypeOptions.length],
  );

  useEffect(() => {
    let mounted = true;

    const loadCompanyConfig = async () => {
      setIsConfigLoading(true);
      try {
        const config = await fetchCompanyConfig();
        if (!mounted) return;

        const roles = (config.roles || []).filter((item): item is 'EMP' | 'INT' | 'HR' =>
          item === 'EMP' || item === 'INT' || item === 'HR',
        );
        setDepartmentOptions(config.departments || []);
        setRoleOptions(roles.length ? roles : ['EMP', 'INT', 'HR']);
        setEmploymentTypeOptions(config.employment_types || []);

        if ((config.departments || []).length > 0) {
          setDepartment((current) => current || config.departments[0]);
        }
        if (roles.length > 0) {
          setRole((current) => (roles.includes(current) ? current : roles[0]));
        }
        if ((config.employment_types || []).length > 0) {
          setEmploymentType((current) => current || config.employment_types[0]);
        }
      } catch (error: any) {
        if (mounted) {
          toast({
            title: 'Company setup required',
            description: error?.message || 'Please complete company setup first.',
            variant: 'destructive',
          });
        }
      } finally {
        if (mounted) setIsConfigLoading(false);
      }
    };

    loadCompanyConfig();
    const handleRealtimeRefresh = (event: Event) => {
      const detail = (event as CustomEvent<RealtimeDataChangedEvent>).detail;
      if (!['accounts.CompanyConfig', 'accounts.CompanyLogo'].includes(detail?.model)) {
        return;
      }
      loadCompanyConfig();
    };
    window.addEventListener(REALTIME_DATA_CHANGED_EVENT, handleRealtimeRefresh);

    return () => {
      mounted = false;
      window.removeEventListener(REALTIME_DATA_CHANGED_EVENT, handleRealtimeRefresh);
    };
  }, [toast]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!hasConfigOptions) {
      toast({
        title: 'Company setup required',
        description: 'Please add departments, roles, and employment types in Company Setup.',
        variant: 'destructive',
      });
      return;
    }
    setIsLoading(true);

    try {
      const data = await createEmployee({
        first_name: firstName,
        last_name: lastName,
        email,
        role,
        date_of_joining: dateOfJoining,
        department: department || undefined,
        employment_type: role === 'HR' ? undefined : (employmentType || undefined),
        // Compensation is set from Payroll, by the organization owner, and is
        // audited there. It is no longer part of creating an employee record,
        // and the directory does not carry it at all (audit V-18).
      });

      setCreated({
        login_id: data.login_id,
        temporary_password: data.temporary_password,
      });

      toast({
        title: 'Employee created',
        description: 'Temporary credentials are ready below.',
      });
    } catch (error: any) {
      const message = error?.message || 'Failed to create employee.';
      toast({
        title: 'Error',
        description: message,
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoToEmployees = () => {
    navigate(employeesPagePath, { state: { refreshKey: Date.now() } });
  };

  return (
    <div className="min-h-screen bg-background">
      <Header breadcrumb="Employees / Create" subtitle="Add a new employee" />

      <div className="p-6">
        <div className="max-w-2xl bg-card rounded-2xl border border-border p-6">
          <h2 className="text-2xl font-bold text-foreground mb-2">Create Employee</h2>
          <p className="text-muted-foreground mb-6">Fill in the details below. A temporary password will be generated.</p>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="flex gap-4">
              <div className="w-1/2">
                <label className="block text-sm font-medium text-foreground mb-2">First Name</label>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                  required
                />
              </div>
              <div className="w-1/2">
                <label className="block text-sm font-medium text-foreground mb-2">Last Name</label>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                  required
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-2">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-foreground mb-2">Salary</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={salary}
                onChange={(e) => setSalary(e.target.value)}
                className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
                required
              />
            </div>

            <div className="flex gap-4">
              <div className="w-1/2">
                <label className="block text-sm font-medium text-foreground mb-2">Role</label>
                <select
                  value={role}
                  onChange={(e) => {
                    const nextRole = e.target.value as 'EMP' | 'INT' | 'HR';
                    setRole(nextRole);
                    if (nextRole === 'HR') {
                      setEmploymentType('');
                    }
                  }}
                  className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {roleOptions
                    .filter((option) => (option === 'HR' ? canCreateHr : true))
                    .map((option) => (
                      <option key={option} value={option}>
                        {option === 'EMP' ? 'Employee' : option === 'INT' ? 'Intern' : 'HR'}
                      </option>
                    ))}
                </select>
              </div>
              <div className="w-1/2">
                <label className="block text-sm font-medium text-foreground mb-2">Date of Joining</label>
                <input
                  type="date"
                  value={dateOfJoining}
                  onChange={(e) => setDateOfJoining(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  required
                />
              </div>
            </div>

            <div className="flex gap-4">
              <div className="w-1/2">
                <label className="block text-sm font-medium text-foreground mb-2">Department</label>
                <select
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {departmentOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </select>
              </div>
              {role !== 'HR' && (
                <div className="w-1/2">
                  <label className="block text-sm font-medium text-foreground mb-2">Employment Type</label>
                  <select
                    value={employmentType}
                    onChange={(e) => setEmploymentType(e.target.value)}
                    className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    {employmentTypeOptions.map((option) => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {!isConfigLoading && !hasConfigOptions && (
              <p className="text-sm text-destructive">
                Company setup is incomplete. Ask admin to fill departments, roles, and employment types.
              </p>
            )}

            <div className="flex items-center gap-3">
              <button
                type="submit"
                disabled={isLoading || isConfigLoading || !hasConfigOptions}
                className="px-5 py-2.5 rounded-xl bg-primary text-primary-foreground font-medium hover:bg-primary/90 transition-colors disabled:opacity-60"
              >
                {isLoading ? 'Creating...' : 'Create Employee'}
              </button>
              <button
                type="button"
                onClick={() => navigate(employeesPagePath)}
                className="px-5 py-2.5 rounded-xl border border-border text-foreground hover:bg-accent transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>

          {created && (
            <div className="mt-8 rounded-xl border border-border bg-muted/40 p-4">
              <p className="text-sm font-medium text-foreground mb-2">Temporary Credentials</p>
              <div className="text-sm text-muted-foreground">Login ID: <span className="font-mono text-foreground">{created.login_id}</span></div>
              <div className="text-sm text-muted-foreground">Temp Password: <span className="font-mono text-foreground">{created.temporary_password}</span></div>
              <button
                onClick={handleGoToEmployees}
                className="mt-4 px-4 py-2 rounded-lg bg-card border border-border text-foreground hover:bg-accent transition-colors"
              >
                Go to Employees
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default CreateEmployee;
