"use client";
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Eye, EyeOff, Loader2 } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import { useAdminStore } from '@/store/adminStore';

const AdminLoginPage = () => {
  const router = useRouter();
  const { toast } = useToast();
  const login = useAdminStore((state) => state.login);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    const result = await login(email, password);

    if (result.success) {
      toast({
        title: 'Welcome back!',
        description: 'You have successfully logged in.',
      });
      router.push('/admin/dashboard');
    } else {
      toast({
        title: 'Login failed',
        description: result.message ?? 'Invalid credentials.',
        // variant: 'destructive',
      });
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-linear-to-b from-[#1a3a47] to-[#0f2935] flex flex-col px-4 py-2 relative overflow-hidden">
      {/* Decorative background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 left-10 w-1 h-1 bg-white/20 rounded-full"></div>
        <div className="absolute top-40 right-20 w-1.5 h-1.5 bg-white/15 rounded-full"></div>
        <div className="absolute top-32 left-1/3 w-1 h-1 bg-white/25 rounded-full"></div>
        <div className="absolute top-1/2 right-1/4 w-1 h-1 bg-white/10 rounded-full"></div>
        <div className="absolute bottom-40 left-1/4 w-1.5 h-1.5 bg-white/20 rounded-full"></div>
        <div className="absolute bottom-32 right-1/3 w-1 h-1 bg-white/15 rounded-full"></div>
      </div>

      {/* Header */}
      <header className="w-full max-w-6xl mx-auto flex items-center justify-between pt-4 pb-8 md:pb-12 relative z-10">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-emerald-400 rounded-full flex items-center justify-center">
            <span className="font-bold text-[#1a3a47] text-lg">E</span>
          </div>
          <span className="text-white font-semibold text-sm hidden sm:inline">Elegance Shawls</span>
        </div>
        <button className="text-white/70 hover:text-white text-xs sm:text-sm flex items-center gap-1 transition-colors">
          <span>ADD LINKS</span>
          <span>EN</span>
        </button>
      </header>

      {/* Main Content */}
      <div className="w-full flex-1 flex items-center justify-center pb-16 md:pb-24 relative z-10">
        <div className="w-full max-w-md animate-fade-up">
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <div className="w-16 h-16 bg-emerald-400 rounded-full flex items-center justify-center">
            <span className="font-bold text-[#1a3a47] text-4xl">E</span>
          </div>
        </div>

        {/* Heading */}
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-5xl font-light text-white mb-2">Admin Login</h1>
         
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-4 md:space-y-5">
          {/* Email Input */}
          <div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Login"
              required
              className="w-full px-4 md:px-5 py-3 md:py-3.5 bg-white/10 backdrop-blur-sm border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:border-emerald-400/50 transition-colors text-sm md:text-base"
            />
          </div>

          {/* Password Input */}
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              className="w-full px-4 md:px-5 py-3 md:py-3.5 bg-white/10 backdrop-blur-sm border border-white/20 rounded-lg text-white placeholder-white/50 focus:outline-none focus:border-emerald-400/50 transition-colors pr-12 text-sm md:text-base"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-black/50 hover:text-black/70 transition-colors"
            >
              {showPassword ? (
                <EyeOff className="w-4 h-4 md:w-5 md:h-5" />
              ) : (
                <Eye className="w-4 h-4 md:w-5 md:h-5" />
              )}
            </button>
          </div>

          
          {/* Login Button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 md:py-3.5 bg-emerald-400 hover:bg-emerald-500 text-[#1a3a47] font-semibold rounded-lg transition-all duration-300 transform hover:scale-105 active:scale-95 disabled:opacity-75 disabled:cursor-not-allowed mt-6 md:mt-8 text-sm md:text-base flex items-center justify-center gap-2"
          >
            {loading && <Loader2 className="w-4 h-4 md:w-5 md:h-5 animate-spin" />}
            Login
          </button>
        </form>
      </div>
      </div>

      {/* Wavy Bottom Design */}
      <div className="absolute bottom-0 left-0 right-0 w-full h-32 md:h-48 pointer-events-none">
        <svg viewBox="0 0 1440 320" preserveAspectRatio="none" className="w-full h-full">
          {/* First wave - Dark teal */}
          <path
            fill="#164e63"
            fillOpacity="0.4"
            d="M0,96L48,112C96,128,192,160,288,165.3C384,171,480,149,576,144C672,139,768,149,864,160C960,171,1056,181,1152,176C1248,171,1344,149,1392,138.7L1440,128L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"
          ></path>
          {/* Second wave - Medium teal */}
          <path
            fill="#1e6b7e"
            fillOpacity="0.3"
            d="M0,160L48,176C96,192,192,224,288,213.3C384,203,480,149,576,144C672,139,768,181,864,197.3C960,213,1056,203,1152,192C1248,181,1344,171,1392,165.3L1440,160L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"
          ></path>
          {/* Third wave - Light gray-blue */}
          <path
            fill="#d9e8ed"
            fillOpacity="0.8"
            d="M0,224L48,234.7C96,245,192,267,288,272C384,277,480,267,576,256C672,245,768,235,864,234.7C960,235,1056,245,1152,250.7C1248,256,1344,256,1392,256L1440,256L1440,320L1392,320C1344,320,1248,320,1152,320C1056,320,960,320,864,320C768,320,672,320,576,320C480,320,384,320,288,320C192,320,96,320,48,320L0,320Z"
          ></path>
        </svg>
      </div>

      {/* Footer */}
      {/* <footer className="absolute bottom-2 md:bottom-4 left-0 right-0 text-center text-xs md:text-sm text-white/40 pointer-events-none">
        <p>This is Recruitify. All rights reserved.</p>
        <p className="text-[10px] md:text-xs">Designed by Luboš Everett</p>
      </footer> */}
    </div>
  
  );
};

export default AdminLoginPage;
