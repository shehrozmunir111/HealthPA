import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { login as apiLogin, session } from "./api";

interface AuthState {
  token: string | null;
  email: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);
const EMAIL_KEY = "healthpa_email";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(session.token());
  const [email, setEmail] = useState<string | null>(
    localStorage.getItem(EMAIL_KEY)
  );

  const value = useMemo<AuthState>(
    () => ({
      token,
      email,
      async signIn(emailInput, password) {
        await apiLogin(emailInput, password);
        localStorage.setItem(EMAIL_KEY, emailInput);
        setToken(session.token());
        setEmail(emailInput);
      },
      signOut() {
        session.clear();
        localStorage.removeItem(EMAIL_KEY);
        setToken(null);
        setEmail(null);
      },
    }),
    [token, email]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
