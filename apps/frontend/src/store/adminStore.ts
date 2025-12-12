import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { API_ENDPOINTS } from '@/config/api.config';

type LoginResult = { success: boolean; message?: string };

interface AdminStore {
  isAuthenticated: boolean;
  token: string | null;
  adminEmail: string | null;
  login: (email: string, password: string) => Promise<LoginResult>;
  logout: () => void;
}

export const useAdminStore = create<AdminStore>()(
  persist(
    (set) => ({
      isAuthenticated: false,
      token: null,
      adminEmail: null,

      login: async (email: string, password: string): Promise<LoginResult> => {
        try {
          const loginResponse = await fetch(API_ENDPOINTS.LOGIN, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
          });

          if (!loginResponse.ok) {
            const errorBody = await loginResponse.json().catch(() => ({}));
            return {
              success: false,
              message: errorBody.detail ?? 'Invalid email or password.',
            };
          }

          const { access_token: accessToken } = await loginResponse.json();
          if (!accessToken) {
            return {
              success: false,
              message: 'Unable to login. Missing access token from server.',
            };
          }

          const userResponse = await fetch(API_ENDPOINTS.CURRENT_USER, {
            headers: {
              Authorization: `Bearer ${accessToken}`,
            },
          });

          if (!userResponse.ok) {
            const errorBody = await userResponse.json().catch(() => ({}));
            return {
              success: false,
              message: errorBody.detail ?? 'Unable to fetch admin profile.',
            };
          }

          const user = await userResponse.json();
          if (!user || user.role !== 'admin') {
            return {
              success: false,
              message: 'You are not authorized to access the admin dashboard.',
            };
          }

          set({
            isAuthenticated: true,
            token: accessToken,
            adminEmail: user.email ?? email,
          });

          return { success: true };
        } catch (error) {
          console.error('Admin login failed', error);
          return {
            success: false,
            message: 'Unable to login right now. Please try again.',
          };
        }
      },

      logout: () => {
        set({ isAuthenticated: false, token: null, adminEmail: null });
      },
    }),
    {
      name: 'admin-auth-storage',
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
        token: state.token,
        adminEmail: state.adminEmail,
      }),
    }
  )
);
