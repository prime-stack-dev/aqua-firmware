"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorKey } from "./api";
import type { MessageKey } from "./messages";

interface State<T> {
  data?: T;
  error?: MessageKey;
  loading: boolean;
}

const REFRESH_MS = 30_000;

/** Load data now and refresh it every 30 seconds while the tab is visible. */
export function usePolled<T>(load: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<State<T>>({ loading: true });
  const loadRef = useRef(load);
  loadRef.current = load;
  const latestRequest = useRef(0);

  const reload = useCallback(async () => {
    const request = ++latestRequest.current;
    try {
      const data = await loadRef.current();
      if (request === latestRequest.current) setState({ data, loading: false });
    } catch (error) {
      // Earlier data stays on screen, with the error shown above it.
      if (request === latestRequest.current) {
        setState((current) => ({ ...current, error: errorKey(error), loading: false }));
      }
    }
  }, []);

  useEffect(() => {
    setState({ loading: true });
    void reload();
    const timer = setInterval(() => {
      if (!document.hidden) void reload();
    }, REFRESH_MS);
    return () => {
      clearInterval(timer);
      latestRequest.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { ...state, reload };
}
