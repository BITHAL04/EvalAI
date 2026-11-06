"use client";

import { ClerkProvider, useAuth, useClerk } from "@clerk/nextjs";
import { createContext, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { AUTH_MODE, CLERK_KEY } from "./config";

type AuthState = { ready: boolean; signedIn: boolean; getToken: () => Promise<string | null>; signOut: () => Promise<void> };
const Ctx = createContext<AuthState>({ ready: true, signedIn: false, getToken: async () => null, signOut: async () => {} });
export const useSession = () => useContext(Ctx);
export const TEST_TOKEN_KEY = "evalai_test_token";

function ClerkBridge({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn, getToken } = useAuth();
  const clerk = useClerk();
  const value = useMemo<AuthState>(
    () => ({ ready: isLoaded, signedIn: !!isSignedIn, getToken: () => getToken(), signOut: () => clerk.signOut({ redirectUrl: "/" }) }),
    [isLoaded, isSignedIn, getToken, clerk],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

function TestBridge({ children }: { children: ReactNode }) {
  const subscribe = (cb: () => void) => { window.addEventListener("storage", cb); return () => window.removeEventListener("storage", cb); };
  const token = useSyncExternalStore(subscribe, () => { try { return localStorage.getItem(TEST_TOKEN_KEY); } catch { return null; } }, () => null);
  const ready = useSyncExternalStore(subscribe, () => true, () => false);
  const value = useMemo<AuthState>(() => ({
    ready, signedIn: !!token, getToken: async () => token,
    signOut: async () => { try { localStorage.removeItem(TEST_TOKEN_KEY); } catch {} window.location.href = "/"; },
  }), [ready, token]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  if (AUTH_MODE === "clerk") {
    return (
      <ClerkProvider publishableKey={CLERK_KEY} signInUrl="/sign-in" signUpUrl="/sign-up" signInFallbackRedirectUrl="/dashboard" signUpFallbackRedirectUrl="/dashboard">
        <ClerkBridge>{children}</ClerkBridge>
      </ClerkProvider>
    );
  }
  if (AUTH_MODE === "test") return <TestBridge>{children}</TestBridge>;
  return <Ctx.Provider value={{ ready: true, signedIn: false, getToken: async () => null, signOut: async () => {} }}>{children}</Ctx.Provider>;
}
