import { useCallback } from 'react';
import { api } from '../api/client';
import { usePolling } from '../hooks/useAuth';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function StatCard({ label, value, icon, color = 'blue' }: {
  label: string;
  value: string | number;
  icon: string;
  color?: string;
}) {
  const colors: Record<string, string> = {
    blue: 'from-blue-600/20 to-blue-600/5 border-blue-600/30',
    green: 'from-emerald-600/20 to-emerald-600/5 border-emerald-600/30',
    red: 'from-red-600/20 to-red-600/5 border-red-600/30',
    amber: 'from-amber-600/20 to-amber-600/5 border-amber-600/30',
    purple: 'from-purple-600/20 to-purple-600/5 border-purple-600/30',
  };

  return (
    <div className={`bg-gradient-to-br ${colors[color]} border rounded-xl p-5`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-gray-400 mb-1">{label}</p>
          <p className="text-2xl font-bold text-white">{value}</p>
        </div>
        <span className="text-2xl opacity-70">{icon}</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const fetchStatus = useCallback(() => api.getStatus(), []);
  const { data: status, loading, error } = usePolling(fetchStatus, 5000);

  if (loading && !status) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-800 rounded-xl p-6 text-red-400">
        加载失败: {error.message}
      </div>
    );
  }

  const messages = status?.messages || { total: 0, done: 0, errors: 0, pending: 0 };
  const storage = status?.storage || {};
  const scheduler = status?.scheduler || { running: false };
  const recentLogs = status?.recent_logs || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">仪表盘</h1>
          <p className="text-gray-500 mt-1">归档系统运行状态总览</p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${scheduler.running ? 'bg-emerald-500 animate-pulse' : 'bg-gray-600'}`} />
          <span className="text-sm text-gray-400">
            {scheduler.running ? '自动扫描运行中' : '自动扫描已停止'}
          </span>
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="已归档" value={messages.done} icon="✅" color="green" />
        <StatCard label="待处理" value={messages.pending} icon="⏳" color="amber" />
        <StatCard label="失败" value={messages.errors} icon="❌" color="red" />
        <StatCard label="总计" value={messages.total} icon="📊" color="blue" />
      </div>

      {/* Storage info */}
      {storage.total > 0 && (
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
          <h2 className="text-sm font-medium text-gray-400 mb-3">存储空间</h2>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-600 to-blue-400 rounded-full transition-all"
                  style={{ width: `${Math.min(100, (storage.used / storage.total) * 100)}%` }}
                />
              </div>
            </div>
            <span className="text-sm text-gray-400 whitespace-nowrap">
              {formatBytes(storage.used)} / {formatBytes(storage.total)}
            </span>
          </div>
        </div>
      )}

      {/* Recent activity */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-5">
        <h2 className="text-sm font-medium text-gray-400 mb-4">最近活动</h2>
        {recentLogs.length === 0 ? (
          <p className="text-gray-600 text-sm">暂无活动记录</p>
        ) : (
          <div className="space-y-2">
            {recentLogs.slice(0, 10).map((log: any, i: number) => (
              <div key={i} className="flex items-start gap-3 text-sm">
                <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${
                  log.level === 'error' ? 'bg-red-500' :
                  log.level === 'warn' ? 'bg-amber-500' : 'bg-emerald-500'
                }`} />
                <span className="text-gray-500 flex-shrink-0 w-36">
                  {new Date(log.timestamp * 1000).toLocaleString('zh-CN')}
                </span>
                <span className="text-gray-300">{log.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <button
          onClick={() => api.rescan()}
          className="bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-blue-600/50 rounded-xl p-5 text-left transition-all group"
        >
          <div className="flex items-center gap-3">
            <span className="text-2xl group-hover:scale-110 transition-transform">🔄</span>
            <div>
              <p className="font-medium text-white">立即扫描</p>
              <p className="text-sm text-gray-500">手动触发频道扫描和归档</p>
            </div>
          </div>
        </button>

        <button
          onClick={() => api.retryFailed()}
          className="bg-gray-900 hover:bg-gray-800 border border-gray-800 hover:border-amber-600/50 rounded-xl p-5 text-left transition-all group"
        >
          <div className="flex items-center gap-3">
            <span className="text-2xl group-hover:scale-110 transition-transform">🔁</span>
            <div>
              <p className="font-medium text-white">重试失败任务</p>
              <p className="text-sm text-gray-500">重新尝试所有失败的归档任务</p>
            </div>
          </div>
        </button>
      </div>
    </div>
  );
}
