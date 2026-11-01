"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "../lib/session";

export default function Home() {
  const { ready, session } = useSession();
  const router = useRouter();
  useEffect(() => {
    if (!ready) return;
    if (!session) router.replace("/login");
    else router.replace(session.role === "coordinator" ? "/coordinator" : "/mock");
  }, [ready, session, router]);
  return null;
}
