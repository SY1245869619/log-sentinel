export interface AuthUser {
  id: number;
  username: string;
  real_name?: string;
  roles: string[];
}

export function getUser(): AuthUser | null {
  try {
    return JSON.parse(localStorage.getItem('user') || 'null');
  } catch {
    return null;
  }
}

export function isLoggedIn(): boolean {
  return !!localStorage.getItem('access_token');
}

export function getToken(): string {
  return localStorage.getItem('access_token') || '';
}

export function hasRole(...roles: string[]): boolean {
  const user = getUser();
  return !!user && roles.some((r) => user.roles.includes(r));
}

export function logout(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  window.location.href = '/login';
}
