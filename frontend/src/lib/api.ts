import type {
  AskResult,
  ExtractResult,
  Hospital,
  PaCase,
  PaStatus,
  ProposedCode,
  ReviewResult,
} from "./types";

const TOKEN_KEY = "healthpa_token";

export const session = {
  token: () => localStorage.getItem(TOKEN_KEY),
  set(token: string) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
};

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 30000
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init.headers as Record<string, string>),
  };
  const token = session.token();
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(path, { ...init, headers, signal: controller.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(
        `Request timed out after ${Math.round(timeoutMs / 1000)}s — the model may be slow or unavailable.`
      );
    }
    throw new Error("Network error — is the API server running?");
  } finally {
    clearTimeout(timer);
  }

  if (!res.ok) {
    const body = await res.text();
    let msg = `${res.status} ${res.statusText}`;
    try {
      const parsed = JSON.parse(body);
      msg = parsed.message || parsed.detail || msg;
    } catch {
      msg = body || msg;
    }
    throw new Error(msg);
  }
  return (await res.json()) as T;
}

export async function login(
  email: string,
  password: string
): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!res.ok) {
    const body = await res.text();
    let msg = "Login failed";
    try {
      const parsed = JSON.parse(body);
      msg = parsed.message || parsed.detail || msg;
    } catch {
      msg = body || msg;
    }
    throw new Error(msg);
  }
  const data = (await res.json()) as { access_token: string };
  session.set(data.access_token);
}

interface BackendPa {
  id: string;
  request_number: string;
  payer_name?: string;
  patient_name?: string;
  status?: PaStatus;
  created_at?: string;
  clinical_notes?: string;
}

function mapPa(row: BackendPa): PaCase {
  return {
    id: row.id,
    request_number: row.request_number ?? row.id,
    patient: row.patient_name ?? "—",
    payer: row.payer_name ?? "—",
    status: (row.status ?? "draft") as PaStatus,
    created_at: row.created_at ?? new Date().toISOString(),
    clinical_notes: row.clinical_notes ?? "",
  };
}

export function listCases(): Promise<PaCase[]> {
  return request<BackendPa[]>("/api/pa-requests/").then((rows) =>
    rows.map(mapPa)
  );
}

export function listHospitals(): Promise<Hospital[]> {
  return request<Hospital[]>("/api/hospitals/public");
}

export async function getCase(id: string): Promise<PaCase> {
  return mapPa(await request<BackendPa>(`/api/pa-requests/${id}`));
}

// Long timeout: grounded extraction runs the LangGraph + LLM, slow on a local model.
export function extract(id: string): Promise<ExtractResult> {
  return request<ExtractResult>(`/api/v1/pa/${id}/extract`, { method: "POST" }, 240000);
}

export function review(
  id: string,
  decision: "approve" | "reject" | "edit",
  editedCodes?: ProposedCode[]
): Promise<ReviewResult> {
  return request<ReviewResult>(
    `/api/v1/pa/${id}/review`,
    {
      method: "POST",
      body: JSON.stringify({ decision, edited_codes: editedCodes }),
    },
    120000
  );
}

export async function register(data: {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  hospital_id: string;
}): Promise<void> {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.text();
    let msg = "Registration failed";
    try {
      const parsed = JSON.parse(body);
      msg = parsed.message || parsed.detail || msg;
    } catch {
      msg = body || msg;
    }
    throw new Error(msg);
  }
}

export function ask(id: string, message: string): Promise<AskResult> {
  return request<AskResult>(
    `/api/v1/pa/${id}/ask`,
    { method: "POST", body: JSON.stringify({ message }) },
    180000
  );
}
