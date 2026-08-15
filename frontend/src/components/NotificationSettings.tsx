import { FormEvent, useEffect, useState } from 'react';
import { Bell, Bot, CheckCircle2, Radio, Send, Webhook } from 'lucide-react';
import { api } from '../api/client';

type ChannelKey = 'telegram' | 'discord' | 'qq' | 'webhook';
type EventKey = 'archive.success' | 'archive.failure' | 'scan.summary' | 'retry.summary';

const EVENT_OPTIONS: { key: EventKey; label: string; hint: string }[] = [
  { key: 'archive.success', label: '单文件成功', hint: '每个文件完成后通知，任务多时消息较多' },
  { key: 'archive.failure', label: '单文件失败', hint: '下载或上传失败时立即通知' },
  { key: 'scan.summary', label: '扫描摘要', hint: '每轮扫描结束后汇报成功、跳过和失败数' },
  { key: 'retry.summary', label: '重试摘要', hint: '失败任务重试后汇报恢复情况' },
];

const EMPTY = {
  app_name: 'TG Archive', events: ['archive.failure', 'scan.summary', 'retry.summary'] as EventKey[], timeout_seconds: 10,
  telegram_enabled: false, telegram_bot_token: '', telegram_chat_id: '', telegram_token_set: false,
  discord_enabled: false, discord_webhook_url: '', discord_webhook_set: false,
  qq_enabled: false, qq_api_url: 'http://127.0.0.1:3000', qq_access_token: '', qq_target_type: 'group', qq_target_id: '', qq_token_set: false,
  webhook_enabled: false, webhook_url: '', webhook_url_set: false, webhook_secret: '', webhook_secret_set: false,
};

export default function NotificationSettings() {
  const [form, setForm] = useState<any>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    api.getNotifications().then((data) => setForm({ ...EMPTY, ...data })).catch((err) => {
      setNotice({ ok: false, text: `通知配置加载失败：${err.message}` });
    });
  }, []);

  const set = (key: string, value: any) => setForm((current: any) => ({ ...current, [key]: value }));
  const toggleEvent = (event: EventKey) => set('events', form.events.includes(event)
    ? form.events.filter((item: EventKey) => item !== event)
    : [...form.events, event]);

  const payload = () => ({
    app_name: form.app_name, events: form.events, timeout_seconds: Number(form.timeout_seconds),
    telegram_enabled: form.telegram_enabled, telegram_bot_token: form.telegram_bot_token || '', telegram_chat_id: form.telegram_chat_id,
    discord_enabled: form.discord_enabled, discord_webhook_url: form.discord_webhook_url || '',
    qq_enabled: form.qq_enabled, qq_api_url: form.qq_api_url, qq_access_token: form.qq_access_token || '', qq_target_type: form.qq_target_type, qq_target_id: form.qq_target_id,
    webhook_enabled: form.webhook_enabled, webhook_url: form.webhook_url, webhook_secret: form.webhook_secret || '',
  });

  const save = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setNotice(null);
    try {
      const result = await api.updateNotifications(payload());
      setForm((current: any) => ({ ...current, ...result, telegram_bot_token: '', discord_webhook_url: '', qq_access_token: '', webhook_secret: '' }));
      setNotice({ ok: true, text: '通知设置已保存，立即生效并会在重启后保留。' });
    } catch (err: any) { setNotice({ ok: false, text: err.message }); }
    finally { setBusy(false); }
  };

  const test = async () => {
    setBusy(true); setNotice(null);
    try {
      const saved = await api.updateNotifications(payload());
      setForm((current: any) => ({ ...current, ...saved, telegram_bot_token: '', discord_webhook_url: '', qq_access_token: '', webhook_url: '', webhook_secret: '' }));
      const result = await api.testNotifications();
      const detail = result.results.map((item: any) => `${item.channel}: ${item.delivered ? '成功' : item.error}`).join('；');
      setNotice({ ok: result.failed === 0 && result.delivered > 0, text: result.delivered ? `测试完成：${detail}` : '没有可测试的渠道，请先启用并填写渠道信息。' });
    } catch (err: any) { setNotice({ ok: false, text: err.message }); }
    finally { setBusy(false); }
  };

  const channel = (key: ChannelKey, title: string, subtitle: string, icon: JSX.Element, fields: JSX.Element) => (
    <section className={`rounded-xl border transition-colors ${form[`${key}_enabled`] ? 'border-blue-500/50 bg-blue-950/20' : 'border-gray-800 bg-gray-950/30'}`}>
      <label className="flex cursor-pointer items-center gap-3 p-4 sm:p-5">
        <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-lg ${form[`${key}_enabled`] ? 'bg-blue-500 text-white' : 'bg-gray-800 text-gray-400'}`}>{icon}</span>
        <span className="min-w-0 flex-1"><strong className="block text-white">{title}</strong><span className="block text-xs leading-5 text-gray-500">{subtitle}</span></span>
        <input aria-label={`启用${title}`} type="checkbox" checked={form[`${key}_enabled`]} onChange={(e) => set(`${key}_enabled`, e.target.checked)} className="h-5 w-5 accent-blue-500" />
      </label>
      {form[`${key}_enabled`] && <div className="grid gap-4 border-t border-gray-800 p-4 sm:p-5">{fields}</div>}
    </section>
  );

  const inputClass = 'w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-white placeholder-gray-600 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20';
  const field = (label: string, key: string, placeholder: string, secret = false, note?: string) => <label className="grid gap-1.5 text-sm text-gray-400"><span>{label}</span><input className={inputClass} type={secret ? 'password' : 'text'} value={form[key] || ''} onChange={(e) => set(key, e.target.value)} placeholder={placeholder} /><small className="text-xs text-gray-600">{note}</small></label>;

  return <form onSubmit={save} className="space-y-5 rounded-xl border border-gray-800 bg-gray-900 p-4 sm:p-6">
    <header className="flex items-start gap-3"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-violet-500/15 text-violet-300"><Bell size={22}/></span><div><h2 className="text-lg font-semibold text-white">消息通知</h2><p className="mt-1 text-sm leading-6 text-gray-500">将归档状态同时发送到多个渠道。单个渠道故障不会阻塞转存任务。</p></div></header>
    {notice && <div role="status" className={`rounded-lg border p-3 text-sm ${notice.ok ? 'border-emerald-700 bg-emerald-950/30 text-emerald-300' : 'border-red-800 bg-red-950/30 text-red-300'}`}>{notice.text}</div>}
    <div className="grid gap-4 sm:grid-cols-2">{field('通知来源名称', 'app_name', 'TG Archive')}{field('发送超时（秒）', 'timeout_seconds', '10')}</div>
    <fieldset><legend className="mb-3 text-sm font-medium text-gray-300">发送哪些事件</legend><div className="grid gap-2 lg:grid-cols-2">{EVENT_OPTIONS.map((option) => <label key={option.key} className="flex cursor-pointer gap-3 rounded-lg border border-gray-800 bg-gray-950/30 p-3"><input type="checkbox" checked={form.events.includes(option.key)} onChange={() => toggleEvent(option.key)} className="mt-0.5 h-4 w-4 accent-blue-500"/><span><strong className="block text-sm font-medium text-gray-200">{option.label}</strong><small className="text-xs leading-5 text-gray-600">{option.hint}</small></span></label>)}</div></fieldset>
    <div className="grid gap-3">
      {channel('telegram', 'Telegram Bot', '通过 Bot Token 发送到用户、群组或频道', <Send size={19}/>, <>{field('Bot Token', 'telegram_bot_token', form.telegram_token_set ? '已保存；留空保持不变' : '123456:ABC...', true)}{field('Chat ID', 'telegram_chat_id', '-1001234567890')}</>)}
      {channel('discord', 'Discord', '使用频道的 Incoming Webhook', <Radio size={19}/>, field('Webhook URL', 'discord_webhook_url', form.discord_webhook_set ? '已保存；留空保持不变' : 'https://discord.com/api/webhooks/...', true))}
      {channel('qq', 'QQ Bot · OneBot v11', '连接 NapCat、Lagrange 等 OneBot HTTP 实现', <Bot size={19}/>, <><div className="grid gap-4 sm:grid-cols-2">{field('OneBot HTTP 地址', 'qq_api_url', 'http://napcat:3000')}{field('Access Token（可选）', 'qq_access_token', form.qq_token_set ? '已保存；留空保持不变' : '访问令牌', true)}</div><div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-sm text-gray-400"><span>发送目标</span><select className={inputClass} value={form.qq_target_type} onChange={(e) => set('qq_target_type', e.target.value)}><option value="group">QQ群</option><option value="private">QQ私聊</option></select></label>{field(form.qq_target_type === 'group' ? '群号' : 'QQ号', 'qq_target_id', '123456789')}</div></>)}
      {channel('webhook', '通用 Webhook', '向自定义系统发送 JSON，可用 HMAC-SHA256 验签', <Webhook size={19}/>, <>{field('Webhook URL', 'webhook_url', form.webhook_url_set ? '已保存；留空保持不变' : 'https://example.com/hooks/archive', true)}{field('签名密钥（可选）', 'webhook_secret', form.webhook_secret_set ? '已保存；留空保持不变' : '用于 X-TG-Archive-Signature', true)}</>)}
    </div>
    <div className="flex flex-col-reverse gap-3 border-t border-gray-800 pt-5 sm:flex-row sm:justify-end"><button type="button" onClick={test} disabled={busy} className="inline-flex items-center justify-center gap-2 rounded-lg border border-gray-700 px-4 py-2.5 text-sm text-gray-200 hover:bg-gray-800 disabled:opacity-50"><CheckCircle2 size={17}/>保存并测试</button><button type="submit" disabled={busy} className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-blue-500 disabled:bg-gray-700">{busy ? '处理中…' : '保存通知设置'}</button></div>
  </form>;
}
