// Light/dark theme: preference stored in localStorage ("light" | "dark"); when
// nothing is stored we follow the OS preference live. The actual class on
// <html> is first set by the inline script in index.html (no flash); this hook
// keeps it in sync and powers the toggle.
import { useCallback, useEffect, useState } from "react";

const KEY = "theme";

function readPref() {
  try {
    return localStorage.getItem(KEY); // "light" | "dark" | null
  } catch {
    return null;
  }
}

function systemPrefersDark() {
  return typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function apply(isDark) {
  document.documentElement.classList.toggle("dark", isDark);
}

export function useTheme() {
  const [pref, setPref] = useState(readPref); // null = follow system
  const isDark = pref ? pref === "dark" : systemPrefersDark();

  // Keep the <html> class in sync with the resolved theme.
  useEffect(() => {
    apply(isDark);
  }, [isDark]);

  // While following the system (no explicit preference), react to OS changes.
  useEffect(() => {
    if (pref) return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [pref]);

  const toggle = useCallback(() => {
    setPref((prev) => {
      const currentlyDark = prev ? prev === "dark" : systemPrefersDark();
      const next = currentlyDark ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  return { isDark, toggle };
}
