// API 配置和工具函数

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

function resolveApiUrl(url: string) {
  if (/^https?:\/\//i.test(url)) {
    return url;
  }

  return `${API_URL}${url.startsWith('/') ? url : `/${url}`}`;
}

export function buildAuthenticatedWebSocketUrl(path: string) {
  const token = getToken();
  const wsBaseUrl = API_URL.replace(/^http/i, 'ws');
  const url = new URL(
    path.startsWith('/') ? `${wsBaseUrl}${path}` : `${wsBaseUrl}/${path}`
  );

  if (token) {
    url.searchParams.set('token', token);
  }

  return url.toString();
}

// 获取 token
export function getToken(): string | null {
  return localStorage.getItem('access_token');
}

// 获取用户信息
export function getUser() {
  const userStr = localStorage.getItem('user');
  return userStr ? JSON.parse(userStr) : null;
}

// 检查是否已登录
export function isAuthenticated(): boolean {
  return !!getToken();
}

// 登出
export function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('token_type');
  localStorage.removeItem('user');
}

// 创建带认证的 fetch 请求
export async function authenticatedFetch(url: string, options: RequestInit = {}) {
  const token = getToken();

  const headers = {
    ...options.headers,
    'Authorization': token ? `Bearer ${token}` : '',
  };

  const response = await fetch(resolveApiUrl(url), {
    ...options,
    headers,
  });

  // 如果返回 401，说明 token 过期，跳转到登录页
  if (response.status === 401) {
    logout();
    window.location.href = '/';
    throw new Error('Authentication expired');
  }

  return response;
}

// 修改密码
export async function changePassword(oldPassword: string, newPassword: string) {
  const response = await authenticatedFetch('/api/v1/auth/change-password', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      old_password: oldPassword,
      new_password: newPassword,
    }),
  });

  if (!response.ok) {
    const data = await response.json();
    throw new Error(data.detail || '修改密码失败');
  }

  return await response.json();
}

export { API_URL };
