import { useState, useCallback } from 'react';
import { api } from '../api/client';
import { usePolling } from '../hooks/useAuth';

export default function Logs() {
  const [level, setLevel] = useState<string>('');
  const [page, setPage] = useState(0);
  const limit = 50;

  const fetchLogs = useCallback(
    () => api.getLogs(limit, page * limit, level || undefined),
    [level, page]
  );
  const { data, loading } = usePolling(fetchLogs, 10000);

  const logs = data?.logs || [];
  const total = data?.total || 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">操作日志</h1>
        <p className="text-gray-500 mt-1">系统运行日志和归档记录</p>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        {[
          { value: '', label: '全部' },
          { value: 'info', label: '信息' },
          { value: 'warn', label: '警告' },
          { value: 'error', label: '错误' },
        ].map((f) => (
          <button
            key={f.value}
            onClick={() => { setLevel(f.value); setPage(0); }}
            className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
              level === f.value
                ? 'bg-blue-600/20 text-blue-400 border border-blue-600/30'
                : 'bg-gray-800 text-gray-400 border border-gray-700 hover:border-gray-600'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Log entries */}
      <div className="bg-gray-900 rounded-xl border border-gray-800">
        {loading && logs.length === 0 ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-12 text-gray-600">
            <p className="text-4xl mb-3">📝</p>
            <p>暂无日志记录</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-800/50">
            {logs.map((log: any) => (
              <div key={log.id} className="px-4 py-3 flex items-start gap-3 hover:bg-gray-800/20 transition-colors">
                <span className={`mt-1 w-2 h-2 rounded-full flex-shrink-0 ${
                  log.level === 'error' ? 'bg-red-500' :
                  log.level === 'warn' ? 'bg-amber-500' : 'bg-emerald-500'
                }`} />
                <span className="text-xs text-gray-600 flex-shrink-0 w-36 font-mono">
                  {new Date(log.timestamp * 1000).toLocaleString('zh-CN')}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-gray-300 break-all">{log.message}</p>
                  {log.message_id && (
                    <span className="text-xs text-gray-600">消息 #{log.message_id}</span>
                  )}
                </div>
                <span className={`badge flex-shrink-0 ${
                  log.level === 'error' ? 'badge-error' :
                  log.level === 'warn' ? 'badge-warning' : 'badge-info'
                }`}>
                  {log.level}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="flex items-center justify-between text-sm text-gray-500">
          <span>共 {total} 条</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1 bg-gray-800 rounded border border-gray-700 disabled:opacity-50"
            >
              上一页
            </button>
            <span className="px-3 py-1">{page + 1}</span>
            <button
              onClick={() => setPage(page + 1)}
              disabled={(page + 1) * limit >= total}
              className="px-3 py-1 bg-gray-800 rounded border border-gray-700 disabled:opacity-50"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
