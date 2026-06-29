"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type UserRole = "consumer" | "admin";

export type AuthUser = {
  username: string;
  role: UserRole;
};

type AuthContextValue = {
  currentUser: AuthUser | null;
  isAuthenticated: boolean;
  isReady: boolean;
  login: (username: string, password: string) => AuthUser | null;
  logout: () => void;
};

const STORAGE_KEY = "procuraai.currentUser";

const MOCK_USERS: Array<AuthUser & { password: string }> = [
  { username: "user", password: "user123", role: "consumer" },
  { username: "admin", password: "admin123", role: "admin" }
];

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredUser(): AuthUser | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AuthUser>;
    if (
      typeof parsed.username === "string" &&
      (parsed.role === "consumer" || parsed.role === "admin")
    ) {
      return { username: parsed.username, role: parsed.role };
    }
  } catch {
    window.localStorage.removeItem(STORAGE_KEY);
  }
  return null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    setCurrentUser(readStoredUser());
    setIsReady(true);
  }, []);

  const value = useMemo<AuthContextValue>(() => {
    function login(username: string, password: string) {
      const user = MOCK_USERS.find(
        (item) => item.username === username.trim() && item.password === password
      );
      if (!user) return null;
      const nextUser = { username: user.username, role: user.role };
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextUser));
      setCurrentUser(nextUser);
      return nextUser;
    }

    function logout() {
      window.localStorage.removeItem(STORAGE_KEY);
      setCurrentUser(null);
    }

    return {
      currentUser,
      isAuthenticated: Boolean(currentUser),
      isReady,
      login,
      logout
    };
  }, [currentUser, isReady]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
