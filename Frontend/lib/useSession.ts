"use client";

import type { Session } from "@supabase/supabase-js";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "./supabase";

export function useSession() {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  return { session, loading };
}

/** Like useSession, but sends signed-out visitors to the sign-in page. */
export function useRequireSession() {
  const router = useRouter();
  const state = useSession();

  useEffect(() => {
    if (!state.loading && !state.session) router.replace("/");
  }, [state.loading, state.session, router]);

  return state;
}
