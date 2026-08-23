import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { AuthLayout } from '@/components/auth/AuthLayout';
import { useToast } from '@/hooks/use-toast';
import dayflowLogo from '@/assets/dayflow-logo.png';
import { useAuth } from '@/contexts/AuthContext';
import { Switch } from '@/components/ui/switch';
import { fetchCompanyConfig } from '@/api/companyConfig';

const Login: React.FC = () => {
  const [loginId, setLoginId] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [loginRole, setLoginRole] = useState<'EMP' | 'ADMIN'>('EMP');
  const [isLoading, setIsLoading] = useState(false);
  const { login, logout } = useAuth();
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    const savedLoginId = localStorage.getItem('savedLoginId');
    const savedLoginRole = localStorage.getItem('savedLoginRole');
    if (savedLoginId) {
      setLoginId(savedLoginId);
    }
    if (savedLoginRole === 'ADMIN' || savedLoginRole === 'EMP') {
      setLoginRole(savedLoginRole);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      const user = await login(loginId, password);
      
      if (rememberMe) {
        localStorage.setItem('savedLoginId', loginId);
        localStorage.setItem('savedLoginRole', loginRole);
      } else {
        localStorage.removeItem('savedLoginId');
        localStorage.removeItem('savedLoginRole');
      }

      toast({
        title: 'Welcome back!',
        description: 'You have successfully logged in.',
      });
      const isAdmin = user?.role === 'ADMIN' || user?.role === 'HR';

      if (loginRole === 'ADMIN') {
        if (!isAdmin) {
          toast({
            title: 'Access denied',
            description: 'Your account is not an Admin account.',
            variant: 'destructive',
          });
          logout();
          return;
        }
        if (user?.role === 'ADMIN') {
          try {
            const config = await fetchCompanyConfig();
            const isConfigured =
              (config.departments?.length ?? 0) > 0 &&
              (config.roles?.length ?? 0) > 0 &&
              (config.employment_types?.length ?? 0) > 0;
            if (!isConfigured) {
              navigate('/company/setup');
              return;
            }
          } catch {
            navigate('/company/setup');
            return;
          }
        }
        navigate('/dashboard/admin');
      } else {
        if (isAdmin) {
          toast({
            title: 'Access denied',
            description: 'Admin/HR accounts must login through Admin.',
            variant: 'destructive',
          });
          logout();
          return;
        }
        navigate('/dashboard/employee');
      }
    } catch (error: any) {
      toast({
        title: 'Login failed',
        description: error?.message || 'Invalid email or password.',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);  
    }
  };

  return (
    <AuthLayout
      quote="Time is what we want most, but what we use worst."
      author="William Penn"
    >
      <div className="bg-card rounded-2xl shadow-medium p-8 md:p-12 border border-border">
        {/* Mobile Logo */}
        <div className="lg:hidden flex items-center gap-2 mb-8">
          <img src={dayflowLogo} alt="Dayflow" className="h-10 w-auto object-contain" />
        </div>

        <h1 className="text-2xl md:text-3xl font-bold text-foreground mb-2">
          Welcome Back
        </h1>
        <p className="text-muted-foreground mb-8">
          Login to your Dayflow account
        </p>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Email/ID Input */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Email or Employee ID
            </label>
            <input
              type="text"
              value={loginId}
              onChange={(e) => setLoginId(e.target.value)}
              placeholder="you@company.com or EMP001"
              className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all"
              required
            />
            <p className="text-xs text-muted-foreground mt-1.5">
              You can login with your email address or employee ID
            </p>
          </div>

          {/* Password Input */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Password
            </label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                className="w-full px-4 py-3 rounded-xl border border-input bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-all pr-12"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
              >
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
          </div>

          {/* Remember Me & Forgot Password */}
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
                className="w-4 h-4 rounded border-input text-primary focus:ring-primary"
              />
              <span className="text-sm text-foreground">Remember me</span>
            </label>
            <button type="button" className="text-sm text-primary hover:underline">
              Forgot password?
            </button>
          </div>

          {/* Login As Toggle */}
          <div className="flex items-center justify-between rounded-xl border border-input px-4 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">Login As</p>
              <p className="text-xs text-muted-foreground">
                {loginRole === 'ADMIN' ? 'Admin' : 'Employee'}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className={`text-xs ${loginRole === 'EMP' ? 'text-foreground' : 'text-muted-foreground'}`}>
                Employee
              </span>
              <Switch
                checked={loginRole === 'ADMIN'}
                onCheckedChange={(checked) => setLoginRole(checked ? 'ADMIN' : 'EMP')}
                aria-label="Toggle admin login"
              />
              <span className={`text-xs ${loginRole === 'ADMIN' ? 'text-foreground' : 'text-muted-foreground'}`}>
                Admin
              </span>
            </div>
          </div>

          {/* Login Button */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3.5 bg-primary text-primary-foreground rounded-xl font-semibold hover:bg-orchid-dark transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Logging in...' : 'Login'}
          </button>
        </form>

        {/* Divider */}
        <div className="flex items-center gap-4 my-6">
          <div className="flex-1 h-px bg-border" />
          <span className="text-sm text-muted-foreground">or</span>
          <div className="flex-1 h-px bg-border" />
        </div>

        {/* Sign Up Link */}
        <p className="text-center text-muted-foreground">
          Don't have an account?{' '}
          <Link to="/signup" className="text-primary font-semibold hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
};

export default Login;
