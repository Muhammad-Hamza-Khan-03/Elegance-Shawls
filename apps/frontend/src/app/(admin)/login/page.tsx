// "use client";
// import { useState } from 'react';
// import { useRouter } from 'next/navigation';
// import { Eye, EyeOff, Loader2 } from 'lucide-react';
// import { Button } from '@/components/ui/button';
// import { Input } from '@/components/ui/input';
// import { Label } from '@/components/ui/label';
// import { useToast } from '@/hooks/use-toast';
// import { useAdminStore } from '@/store/adminStore';

// const AdminLoginPage = () => {
//   const router = useRouter();
//   const { toast } = useToast();
//   const login = useAdminStore((state) => state.login);

//   const [email, setEmail] = useState('');
//   const [password, setPassword] = useState('');
//   const [showPassword, setShowPassword] = useState(false);
//   const [loading, setLoading] = useState(false);

//   const handleSubmit = async (e: React.FormEvent) => {
//     e.preventDefault();
//     setLoading(true);

//     // Simulate API call
//     await new Promise((resolve) => setTimeout(resolve, 500));

//     const success = login(email, password);

//     if (success) {
//       toast({
//         title: 'Welcome back!',
//         description: 'You have successfully logged in.',
//       });
//       router.push('/admin');
//     } else {
//       toast({
//         title: 'Login failed',
//         description: 'Invalid credentials. Use password: admin123',
//         variant: 'destructive',
//       });
//     }

//     setLoading(false);
//   };

//   return (
//     <div className="min-h-screen flex items-center justify-center bg-gradient-subtle p-4">
//       <div className="w-full max-w-md">
//         <div className="bg-card rounded-xl shadow-elevated p-8">
//           <div className="text-center mb-8">
//             <h1 className="font-heading text-2xl font-bold text-primary">Admin Login</h1>
//             <p className="text-muted-foreground mt-2">
//               Enter your credentials to access the dashboard
//             </p>
//           </div>

//           <form onSubmit={handleSubmit} className="space-y-6">
//             <div className="space-y-2">
//               <Label htmlFor="email">Email</Label>
//               <Input
//                 id="email"
//                 type="email"
//                 value={email}
//                 onChange={(e) => setEmail(e.target.value)}
//                 placeholder="admin@example.com"
//                 required
//               />
//             </div>

//             <div className="space-y-2">
//               <Label htmlFor="password">Password</Label>
//               <div className="relative">
//                 <Input
//                   id="password"
//                   type={showPassword ? 'text' : 'password'}
//                   value={password}
//                   onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
//                   placeholder="••••••••"
//                   required
//                 />
//                 <button
//                   type="button"
//                   onClick={() => setShowPassword(!showPassword)}
//                   className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
//                 >
//                   {showPassword ? (
//                     <EyeOff className="h-4 w-4" />
//                   ) : (
//                     <Eye className="h-4 w-4" />
//                   )}
//                 </button>
//               </div>
//               <p className="text-xs text-muted-foreground">
//                 Hint: Use password "admin123"
//               </p>
//             </div>

//             <Button type="submit" variant="gold" className="w-full" disabled={loading}>
//               {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
//               Sign In
//             </Button>
//           </form>
//         </div>
//       </div>
//     </div>
//   );
// };

// export default AdminLoginPage;
