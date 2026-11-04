"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function Header({ email }: { email?: string }) {
  const router = useRouter();

  async function signOut() {
    await supabase.auth.signOut();
    router.replace("/");
  }

  return (
    <header className="border-b border-line">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link href="/library" className="text-base font-semibold tracking-tight">
          StudySnap
        </Link>
        <div className="flex items-center gap-3 text-sm">
          {email && <span className="hidden text-muted sm:inline">{email}</span>}
          <button onClick={signOut} className="btn">Sign out</button>
        </div>
      </div>
    </header>
  );
}
