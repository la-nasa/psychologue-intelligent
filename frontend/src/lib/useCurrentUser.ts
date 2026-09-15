"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { ApiError, clearToken, getMe, getToken, MeResponse } from "@/lib/api"

type GuardState = "loading" | "ready" | "denied"

/**
 * Charge le compte connecté et redirige si son rôle ne couvre pas `allowedRoles`.
 * `null`/`undefined` roulé vers /login (pas de session) ; rôle insuffisant vers /.
 */
export function useRoleGuard(allowedRoles: string[]) {
  const router = useRouter()
  const [state, setState] = useState<GuardState>("loading")
  const [me, setMe] = useState<MeResponse | null>(null)

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login")
      return
    }
    let cancelled = false
    getMe()
      .then((res) => {
        if (cancelled) return
        if (!res.roles.some((r) => allowedRoles.includes(r))) {
          setState("denied")
          return
        }
        setMe(res)
        setState("ready")
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 401) {
          clearToken()
          router.replace("/login")
          return
        }
        setState("denied")
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { state, me }
}
