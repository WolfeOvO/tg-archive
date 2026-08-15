/**
 * API client for TG Archive backend.
 */

const API_BASE = '/api';

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('tg-archive-token');
  }

  setToken(token: string) {
    this.token = token;
    localStorage.setItem('tg-archive-token', token);
  }

  clearToken() {
    this.token = null;
    localStorage.removeItem('tg-archive-token');
  }

  isAuthenticated(): boolean {
    return !!this.token;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
    });

    if (res.status === 401) {
      this.clearToken();
      window.location.reload();
      throw new Error('Unauthorized');
    }

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `HTTP ${res.status}`);
    }

    return res.json();
  }

  // Auth
  async login(password: string) {
    const data = await this.request<{ token: string; expires_at: string }>(
      '/auth/login',
      { method: 'POST', body: JSON.stringify({ password }) }
    );
    this.setToken(data.token);
    return data;
  }

  async verifyAuth() {
    return this.request<{ valid: boolean }>('/auth/verify');
  }

  // Status
  async getStatus() {
    return this.request<any>('/status');
  }

  async getStats() {
    return this.request<any>('/stats');
  }

  async getLogs(limit = 50, offset = 0, level?: string) {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (level) params.set('level', level);
    return this.request<any>(`/logs?${params}`);
  }

  // Tasks
  async getTasks(params: { state?: string; channel?: string; limit?: number; offset?: number } = {}) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) searchParams.set(k, String(v));
    });
    return this.request<any>(`/tasks?${searchParams}`);
  }

  async getTask(id: number) {
    return this.request<any>(`/tasks/${id}`);
  }

  async rescan(channel?: string) {
    return this.request<any>('/tasks/rescan', {
      method: 'POST',
      body: JSON.stringify({ channel }),
    });
  }

  async retryFailed() {
    return this.request<any>('/tasks/retry', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }

  async resetTask(id: number) {
    return this.request<any>(`/tasks/reset/${id}`, { method: 'POST' });
  }

  // Config
  async getConfig() {
    return this.request<any>('/config');
  }

  async updateConfig(data: Record<string, any>) {
    return this.request<any>('/config', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async updateCredentials(data: Record<string, any>) {
    return this.request<any>('/config/credentials', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async getNotifications() {
    return this.request<any>('/notifications');
  }

  async updateNotifications(data: Record<string, any>) {
    return this.request<any>('/notifications', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async testNotifications() {
    return this.request<any>('/notifications/test', {
      method: 'POST',
      body: JSON.stringify({}),
    });
  }
}

export const api = new ApiClient();
