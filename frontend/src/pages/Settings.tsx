import { useState, useEffect, FormEvent } from 'react';
import { api } from '../api/client';

export default function Settings() {
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Editable fields
  const [channel, setChannel] = useState('');
  const [cloudType, setCloudType] = useState('local');
  const [localPath, setLocalPath] = useState('');
  const [batchSize, setBatchSize] = useState(10);
  const [retryInterval, setRetryInterval] = useState(300);

  // Credential fields
  const [showCreds, setShowCreds] = useState(false);
  const [tgApiId, setTgApiId] = useState('');
  const [tgApiHash, setTgApiHash] = useState('');
  const [tgSession, setTgSession] = useState('');
  const [pan123Token, setPan123Token] = useState('');
  const [adminPassword, setAdminPassword] = useState('');

  useEffect(() => {
    api.getConfig().then((c) => {
      setConfig(c);
      setChannel(c.tg_channel);
      setCloudType(c.cloud_type);
      setLocalPath(c.cloud_local_path);
      setBatchSize(c.archive_batch_size);
      setRetryInterval(c.retry_interval);
      setLoading(false);
    });
  }, []);

  const handleSaveConfig = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await api.updateConfig({
        tg_channel: channel,
        cloud_type: cloudType,
        cloud_local_path: localPath,
        archive_batch_size: batchSize,
        retry_interval: retryInterval,
      });
      setMessage({ type: 'success', text: '配置已保存' });
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleSaveCreds = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const data: Record<string, any> = {};
      if (tgApiId) data.tg_api_id = parseInt(tgApiId);
      if (tgApiHash) data.tg_api_hash = tgApiHash;
      if (tgSession) data.tg_session_string = tgSession;
      if (pan123Token) data.pan123_access_token = pan123Token;
      if (adminPassword) data.admin_password = adminPassword;

      await api.updateCredentials(data);
      setMessage({ type: 'success', text: '凭据已保存（部分更改需重启生效）' });
      setTgApiHash('');
      setTgSession('');
      setPan123Token('');
      setAdminPassword('');
    } catch (err: any) {
      setMessage({ type: 'error', text: err.message });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-white">设置</h1>
        <p className="text-gray-500 mt-1">配置归档参数和凭据</p>
      </div>

      {message && (
        <div className={`p-4 rounded-lg border ${
          message.type === 'success'
            ? 'bg-emerald-900/20 border-emerald-800 text-emerald-400'
            : 'bg-red-900/20 border-red-800 text-red-400'
        }`}>
          {message.text}
          <button onClick={() => setMessage(null)} className="float-right text-gray-500 hover:text-gray-300">×</button>
        </div>
      )}

      {/* General config */}
      <form onSubmit={handleSaveConfig} className="bg-gray-900 rounded-xl border border-gray-800 p-6 space-y-5">
        <h2 className="text-lg font-semibold text-white">归档配置</h2>

        <div>
          <label className="block text-sm text-gray-400 mb-1.5">目标频道</label>
          <input
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            placeholder="@channel_username 或频道 ID"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1.5">存储后端</label>
          <select
            value={cloudType}
            onChange={(e) => setCloudType(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
          >
            <option value="local">本地存储</option>
            <option value="pan123">123云盘</option>
          </select>
        </div>

        {cloudType === 'local' && (
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">本地存储路径</label>
            <input
              value={localPath}
              onChange={(e) => setLocalPath(e.target.value)}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">每批扫描数量</label>
            <input
              type="number"
              value={batchSize}
              onChange={(e) => setBatchSize(parseInt(e.target.value))}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1.5">扫描间隔（秒）</label>
            <input
              type="number"
              value={retryInterval}
              onChange={(e) => setRetryInterval(parseInt(e.target.value))}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:border-blue-500 focus:outline-none"
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white rounded-lg transition-colors"
        >
          {saving ? '保存中...' : '保存配置'}
        </button>
      </form>

      {/* Credentials */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <button
          onClick={() => setShowCreds(!showCreds)}
          className="w-full flex items-center justify-between text-lg font-semibold text-white"
        >
          <span>凭据管理</span>
          <span className="text-gray-500">{showCreds ? '▲' : '▼'}</span>
        </button>

        {showCreds && (
          <form onSubmit={handleSaveCreds} className="mt-5 space-y-4">
            <p className="text-sm text-amber-400 bg-amber-900/20 border border-amber-800 rounded-lg p-3">
              ⚠️ 修改凭据后需要重启服务才能生效
            </p>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Telegram API ID</label>
              <input
                value={tgApiId}
                onChange={(e) => setTgApiId(e.target.value)}
                placeholder={config?.tg_api_id ? `当前: ${config.tg_api_id}` : '未设置'}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Telegram API Hash</label>
              <input
                value={tgApiHash}
                onChange={(e) => setTgApiHash(e.target.value)}
                placeholder={config?.tg_api_hash ? `当前: ${config.tg_api_hash}` : '未设置'}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">
                Telegram Session String
                <span className="text-gray-600 ml-2">
                  {config?.tg_session_set ? '✅ 已设置' : '❌ 未设置'}
                </span>
              </label>
              <textarea
                value={tgSession}
                onChange={(e) => setTgSession(e.target.value)}
                placeholder="粘贴 session string..."
                rows={3}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none font-mono text-xs"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">
                123云盘 Access Token
                <span className="text-gray-600 ml-2">
                  {config?.pan123_token_set ? '✅ 已设置' : '❌ 未设置'}
                </span>
              </label>
              <input
                value={pan123Token}
                onChange={(e) => setPan123Token(e.target.value)}
                placeholder="粘贴 access token..."
                type="password"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">修改管理密码</label>
              <input
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                placeholder="留空不修改"
                type="password"
                className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-600 focus:border-blue-500 focus:outline-none"
              />
            </div>

            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 text-white rounded-lg transition-colors"
            >
              {saving ? '保存中...' : '保存凭据'}
            </button>
          </form>
        )}
      </div>

      {/* Status info */}
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h2 className="text-lg font-semibold text-white mb-4">系统信息</h2>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">版本</span>
            <span className="text-gray-300">1.0.0</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Telegram API</span>
            <span className="text-gray-300">{config?.tg_api_id ? '已配置' : '未配置'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Session</span>
            <span className="text-gray-300">{config?.tg_session_set ? '有效' : '未设置'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">存储后端</span>
            <span className="text-gray-300">{config?.cloud_type === 'pan123' ? '123云盘' : '本地存储'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
