"use client";

import { ReactNode, createContext, useContext, useEffect, useState } from "react";
import { AppState, initialAppState } from "@/lib/types";

type SessionContextValue = {
  state: AppState;
  hydrateComplete: boolean;
  mergeState: (updates: Partial<AppState>) => void;
  replaceState: (nextState: AppState) => void;
  resetState: () => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);
const STORAGE_KEY = "opendev-ai-v5";

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState>(initialAppState);
  const [hydrateComplete, setHydrateComplete] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        setState(JSON.parse(saved) as AppState);
      } catch {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    }
    setHydrateComplete(true);
  }, []);

  useEffect(() => {
    if (!hydrateComplete) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [hydrateComplete, state]);

  const value: SessionContextValue = {
    state,
    hydrateComplete,
    mergeState: (updates) => setState((current) => ({ ...current, ...updates })),
    replaceState: (nextState) => setState(nextState),
    resetState: () => setState(initialAppState),
  };

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useAppSession() {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useAppSession must be used inside SessionProvider");
  return context;
}
