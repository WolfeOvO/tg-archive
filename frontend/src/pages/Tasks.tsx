import { useState, useCallback } from 'react';
import { api } from '../api/client';
import { usePolling } from '../hooks/useAuth';

function formatBytes(bytes: number): string {
  if (!bytes) return '-';
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function StateBadge({ state }: { state: string }) {
  const map: Record<string, { cls: string; label: string }> = {
    done: { cls: 'badge-success', label: '已完成' },
    error: { cls: 'badge-error', label: '失败' },
    pending: { cls: 'badge-warning', label: '等待中' },
    downloading: { cls: 'badge-info', label: '下载中' },
    uploading: { cls: 'badge-info', label: '上传中' },
  };
  const info = map[state] || { cls: 'badge-neutral', label: state };
  return <span className={`badge ${info.cls}`}>{info.label}</span>;
}

export default function Tasks() {
  const [filter, setFilter] = useState<string>('');
  const [page, setPage] = useState(0);
  const limit = 20;

  const fetchTasks = useCallback(
    () => api.getTasks({ state: filter || undefined, limit, offset: page * limit }),
    [filter, page]
  );
  const { data, loading, refresh } = usePolling(fetchTasks, 8000);

  const tasks = data?.tasks || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / limit);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">归档任务</h1>
          <p className="text-gray-500 mt-1">查看和管理所有归档消息</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => api.rescan()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
          >
            🔄 立即扫描
          </button>
          <button
            onClick={() => api.retryFailed()}
            className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg border border-gray-700 transition-colors"
          >
            🔁 重试失败
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        {[
          { value: '', label: '全部' },
          { value: 'done', label: '已完成' },
          { value: 'pending', label: '等待中' },
          { value: 'downloading', label: '下载中' },
          { value: 'uploading', label: '上传中' },
          { value: 'error', label: '失败' },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => { setFilter(f.value); setPage(0); }}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              filter === f.value
                ? 'bg-blue-600/20 text-blue-400 border border-blue-600/30'
                : 'bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-600'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Task list */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        {loading && tasks.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="text-center py-12 text-gray-600">
            <p className="text-4xl mb-3">📭</p>
            <p>暂无任务记录</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">消息ID</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">状态</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">文件名</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">类型</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">大小</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">时间</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/50">
                {tasks.map((task: any) => (
                  <tr key={task.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="px-4 py-3 text-gray-300 font-mono">{task.id}</td>
                    <td className="px-4 py-3">
                      <StateBadge state={task.state} />
                    </td>
                    <td className="px-4 py-3 text-gray-300 max-w-xs truncate" title={task.file_name}>
                      {task.file_name || '-'}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{task.media_type || '-'}</td>
                    <td className="px-4 py-3 text-gray-500 text-right">{formatBytes(task.file_size)}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {task.updated_at
                        ? new Date(task.updated_at * 1000).toLocaleString('zh-CN', {
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                          })
                        : '-'}
                    </td>
                    <td className="px-4 py-3">
                      {task.state === 'error' && (
                        <button
                          onClick={() => api.resetTask(task.id).then(refresh)}
                          className="text-xs text-amber-400 hover:text-amber-300 transition-colors"
                        >
                          重置
                        </button>
                      )}
                      {task.error && (
                        <span className="text-xs text-red-500 ml-2" title={task.error}>
                          ⚠️
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>共 {total} 条记录</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1 bg-gray-800 rounded border border-gray-700 disabled:opacity-50 hover:border-gray-600 transition-colors"
            >
              上一页
            </button>
            <span className="px-3 py-1">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1 bg-gray-800 rounded border border-gray-700 disabled:opacity-50 hover:border-gray-600 transition-colors"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
