import React, { useEffect, useState } from 'react';
import { Header } from '@/components/layout/Header';
import { AvatarWithBadge } from '@/components/Avatar';
import { Search, Download, MoreVertical, ChevronLeft, ChevronRight, Plus } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { exportEmployees, fetchEmployees, deleteEmployee } from '@/api/employees';
import { REALTIME_DATA_CHANGED_EVENT } from '@/hooks/useRealtimeUpdates';
import { useToast } from '@/hooks/use-toast';

interface Employee {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  login_id: string;
  role: 'ADMIN' | 'HR' | 'EMP' | 'INT';
  date_of_joining: string;
  department: string;
  employment_type: string;
  salary?: number | string | null;
  is_active: boolean;
}

const EmployeesAdmin: React.FC = () => {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRole, setSelectedRole] = useState('all');
  const [selectedEmployees, setSelectedEmployees] = useState<number[]>([]);
  const [isExporting, setIsExporting] = useState(false);

  const [activeMenuEmployeeId, setActiveMenuEmployeeId] = useState<number | null>(null);
  const [employeeToDelete, setEmployeeToDelete] = useState<Employee | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const { toast } = useToast();

  const roles = ['all', 'HR', 'EMP', 'INT'];

  useEffect(() => {
    let isMounted = true;

    const loadEmployees = async () => {
      try {
        const data = await fetchEmployees('non_admin');
        if (isMounted) {
          setEmployees(data);
        }
      } catch (err) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : 'Failed to load employees');
        }
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    };

    loadEmployees();
    const handleRealtimeRefresh = () => {
      loadEmployees();
    };
    window.addEventListener(REALTIME_DATA_CHANGED_EVENT, handleRealtimeRefresh);

    const handleDocumentClick = () => {
      setActiveMenuEmployeeId(null);
    };
    document.addEventListener('click', handleDocumentClick);

    return () => {
      isMounted = false;
      window.removeEventListener(REALTIME_DATA_CHANGED_EVENT, handleRealtimeRefresh);
      document.removeEventListener('click', handleDocumentClick);
    };
  }, [location.state?.refreshKey]);

  const handleDeleteConfirm = async (employeeId: number) => {
    setIsDeleting(true);
    try {
      await deleteEmployee(employeeId);
      setEmployees(prev => prev.filter(emp => emp.id !== employeeId));
      toast({
        title: "Employee deleted",
        description: "The employee has been removed successfully.",
      });
    } catch (err) {
      toast({
        title: "Deletion failed",
        description: err instanceof Error ? err.message : "Failed to delete employee. Try again.",
        variant: "destructive",
      });
    } finally {
      setIsDeleting(false);
      setEmployeeToDelete(null);
    }
  };

  const filteredEmployees = employees.filter(emp => {
    const fullName = `${emp.first_name} ${emp.last_name}`.trim().toLowerCase();
    const matchesSearch = fullName.includes(searchQuery.toLowerCase()) ||
      emp.email.toLowerCase().includes(searchQuery.toLowerCase()) ||
      emp.login_id.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesRole = selectedRole === 'all' || emp.role === selectedRole;
    return matchesSearch && matchesRole;
  });

  const toggleSelectAll = () => {
    if (selectedEmployees.length === filteredEmployees.length) {
      setSelectedEmployees([]);
    } else {
      setSelectedEmployees(filteredEmployees.map(e => e.id));
    }
  };

  const toggleSelectEmployee = (id: number) => {
    setSelectedEmployees(prev =>
      prev.includes(id) ? prev.filter(e => e !== id) : [...prev, id]
    );
  };

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedRole('all');
  };

  const handleRowClick = (employee: Employee) => {
    const isEmployee = employee.role === 'EMP' || employee.role === 'INT';
    navigate(isEmployee ? '/profile/employee' : '/profile/admin');
  };

  const getRoleBadgeType = (role: Employee['role']) =>
    role === 'EMP' || role === 'INT' ? 'employee' : 'admin';
  const getRoleLabel = (role: Employee['role']) => {
    if (role === 'HR') return 'HR';
    if (role === 'INT') return 'Intern';
    return 'Employee';
  };

  const getStatusLabel = (active: boolean) => (active ? 'Active' : 'Inactive');
  const getStatusClass = (active: boolean) =>
    active
      ? 'bg-success text-success-foreground'
      : 'bg-muted text-muted-foreground';
  const formatSalary = (salary?: number | string | null) => {
    if (salary === null || salary === undefined || salary === '') return '--';
    const numeric = typeof salary === 'number' ? salary : Number(salary);
    if (Number.isNaN(numeric)) return '--';
    return numeric.toLocaleString('en-IN', { style: 'currency', currency: 'INR' });
  };

  const handleExport = async () => {
    setIsExporting(true);
    setError(null);
    try {
      const roleFilter = selectedRole === 'all' ? undefined : (selectedRole as 'HR' | 'EMP' | 'INT');
      const { blob, filename } = await exportEmployees('non_admin', roleFilter);
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export employees');
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header breadcrumb="Employees Admin" subtitle="All company users except admin" />

      <div className="p-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Employees Admin</h2>
            <p className="text-muted-foreground">Manage all non-admin users</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('/employees/new')}
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
            >
              <Plus size={18} />
              Add Employee
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting}
              className="inline-flex items-center gap-2 px-4 py-2.5 bg-card border border-border rounded-lg text-foreground hover:bg-accent transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <Download size={18} />
              {isExporting ? 'Exporting...' : 'Export'}
            </button>
          </div>
        </div>

        <div className="bg-card rounded-xl border border-border p-4 mb-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="relative flex-1">
              <Search size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by name, email, or ID..."
                className="w-full pl-10 pr-4 py-2.5 rounded-lg border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <select
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value)}
                className="px-4 py-2.5 rounded-lg border border-input bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary capitalize"
              >
                <option value="all">All Roles</option>
                {roles.slice(1).map(role => (
                  <option key={role} value={role} className="capitalize">{role}</option>
                ))}
              </select>

              <button
                onClick={clearFilters}
                className="px-4 py-2.5 text-muted-foreground hover:text-foreground transition-colors"
              >
                Clear filters
              </button>
            </div>
          </div>
        </div>

        <div className="bg-card rounded-xl border border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left">
                    <input
                      type="checkbox"
                      checked={selectedEmployees.length === filteredEmployees.length && filteredEmployees.length > 0}
                      onChange={toggleSelectAll}
                      className="w-4 h-4 rounded border-input text-primary focus:ring-primary"
                    />
                  </th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Employee</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Employee ID</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Department</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Role</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Type</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Salary</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Status</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Joining Date</th>
                  <th className="px-4 py-3 text-left text-sm font-semibold text-foreground">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {isLoading ? (
                  <tr>
                    <td className="px-4 py-10 text-center text-sm text-muted-foreground" colSpan={10}>
                      Loading employees...
                    </td>
                  </tr>
                ) : error ? (
                  <tr>
                    <td className="px-4 py-10 text-center text-sm text-error" colSpan={10}>
                      {error}
                    </td>
                  </tr>
                ) : filteredEmployees.length === 0 ? (
                  <tr>
                    <td className="px-4 py-10 text-center text-sm text-muted-foreground" colSpan={10}>
                      No employees yet. Add employees to see them here.
                    </td>
                  </tr>
                ) : (
                  filteredEmployees.map((employee) => {
                    const fullName = `${employee.first_name} ${employee.last_name}`.trim() || employee.login_id;
                    return (
                      <tr
                        key={employee.id}
                        className="hover:bg-muted/30 transition-colors cursor-pointer"
                        onClick={() => handleRowClick(employee)}
                      >
                        <td className="px-4 py-4" onClick={(e) => e.stopPropagation()}>
                          <input
                            type="checkbox"
                            checked={selectedEmployees.includes(employee.id)}
                            onChange={() => toggleSelectEmployee(employee.id)}
                            className="w-4 h-4 rounded border-input text-primary focus:ring-primary"
                          />
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-3">
                            <AvatarWithBadge
                              name={fullName}
                              role={getRoleBadgeType(employee.role)}
                              size="sm"
                            />
                            <div>
                              <p className="font-medium text-foreground">{fullName}</p>
                              <p className="text-sm text-muted-foreground">{employee.email}</p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4 text-sm text-foreground font-mono">{employee.login_id}</td>
                        <td className="px-4 py-4 text-sm text-foreground">{employee.department || '--'}</td>
                        <td className="px-4 py-4 text-sm text-foreground">{getRoleLabel(employee.role)}</td>
                        <td className="px-4 py-4 text-sm text-foreground">{employee.employment_type || '--'}</td>
                        <td className="px-4 py-4 text-sm text-foreground">{formatSalary(employee.salary)}</td>
                        <td className="px-4 py-4">
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getStatusClass(employee.is_active)}`}>
                            {getStatusLabel(employee.is_active)}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-sm text-foreground">
                          {new Date(employee.date_of_joining).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                        </td>
                        <td className="px-4 py-4 relative" onClick={(e) => e.stopPropagation()}>
                          <button 
                            onClick={() => setActiveMenuEmployeeId(activeMenuEmployeeId === employee.id ? null : employee.id)}
                            className="p-2 hover:bg-muted rounded-lg transition-colors"
                          >
                            <MoreVertical size={16} className="text-muted-foreground" />
                          </button>

                          {activeMenuEmployeeId === employee.id && (
                            <div className="absolute right-4 mt-1 w-32 bg-popover text-popover-foreground border border-border rounded-lg shadow-lg z-50 py-1">
                              <button
                                onClick={() => {
                                  setActiveMenuEmployeeId(null);
                                  handleRowClick(employee);
                                }}
                                className="w-full text-left px-3 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground transition-colors"
                              >
                                View Profile
                              </button>
                              <button
                                onClick={() => {
                                  setActiveMenuEmployeeId(null);
                                  setEmployeeToDelete(employee);
                                }}
                                className="w-full text-left px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10 transition-colors"
                              >
                                Delete
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="flex items-center justify-between px-4 py-4 border-t border-border">
            <p className="text-sm text-muted-foreground">
              Showing {filteredEmployees.length} of {employees.length} employees
            </p>
            <div className="flex items-center gap-2">
              <button className="p-2 rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50" disabled>
                <ChevronLeft size={16} />
              </button>
              <span className="px-3 py-1 text-sm font-medium text-foreground">1</span>
              <button className="p-2 rounded-lg border border-border hover:bg-muted transition-colors disabled:opacity-50" disabled>
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {employeeToDelete && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card border border-border rounded-xl shadow-lg max-w-md w-full p-6 animate-in fade-in zoom-in-95 duration-150">
            <h3 className="text-lg font-semibold text-foreground mb-2">Delete Employee</h3>
            <p className="text-sm text-muted-foreground mb-6">
              Are you sure you want to delete <span className="font-semibold text-foreground">{employeeToDelete.first_name} {employeeToDelete.last_name}</span>? This action is permanent and will delete all associated payroll and attendance records.
            </p>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setEmployeeToDelete(null)}
                className="px-4 py-2 border border-border rounded-lg text-foreground hover:bg-accent text-sm font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleDeleteConfirm(employeeToDelete.id)}
                disabled={isDeleting}
                className="px-4 py-2 bg-destructive text-destructive-foreground rounded-lg hover:bg-destructive/90 text-sm font-medium transition-colors disabled:opacity-60"
              >
                {isDeleting ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EmployeesAdmin;
