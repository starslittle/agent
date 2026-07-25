export interface AuthUser {
  id: string;
  email: string;
  display_name: string;
  status: string;
  created_at: string;
}

export interface AuthSession {
  authenticated: boolean;
  user?: AuthUser;
  csrf_token?: string;
  expires_at?: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export interface RegisterInput extends LoginInput {
  display_name: string;
}

async function authRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as
      | { error?: string; message?: string }
      | null;
    throw new Error(authErrorMessage(payload?.error, payload?.message));
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export function fetchSession(): Promise<AuthSession> {
  return authRequest<AuthSession>("/api/v1/session");
}

export function login(input: LoginInput): Promise<AuthSession> {
  return authRequest<AuthSession>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function register(input: RegisterInput): Promise<AuthSession> {
  return authRequest<AuthSession>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function logout(csrfToken: string): Promise<void> {
  return authRequest<void>("/api/v1/auth/logout", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

function authErrorMessage(code?: string, detail?: string): string {
  if (detail) return detail;
  switch (code) {
    case "invalid_credentials":
      return "邮箱或密码不正确";
    case "email_already_registered":
      return "这个邮箱已经注册，可以直接登录";
    case "too_many_attempts":
      return "尝试次数过多，请稍后再试";
    case "origin_not_allowed":
    case "origin_required":
      return "当前访问来源未获授权";
    default:
      return "操作没有完成，请稍后重试";
  }
}
