import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const SUPABASE_URL = import.meta.env["VITE_SUPABASE_URL"] || "";
const SUPABASE_ANON_KEY = import.meta.env["VITE_SUPABASE_ANON_KEY"] || "";

/**
 * False in local/demo setups that haven't provisioned a Supabase project yet
 * (VITE_SUPABASE_URL/VITE_SUPABASE_ANON_KEY unset). auth.tsx falls back to the
 * backend's X-Dev-Role bypass in that case (backend/app/auth.py DEV_BYPASS).
 */
export const isSupabaseConfigured = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

export const supabase: SupabaseClient | null = isSupabaseConfigured
  ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    })
  : null;
