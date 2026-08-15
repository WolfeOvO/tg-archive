import { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Database, Plus, Save, Server, Trash2, X } from 'lucide-react';
import { api } from '../api/client';

type Field = { key: string; label: string; type: string; required: boolean; secret: boolean; placeholder: string; default?: any; options?: string[]; help?: string };
type Driver = { key: string; name: string; description: string; fields: Field[] };
type Mount = { id: string; name: string; mount_path: string; driver: string; enabled: boolean; default: boolean; config: Record<string, any>; secret_fields_set: string[] };

const inputClass = 'w-full min-w-0 rounded-lg border border-gray-700 bg-gray-800 px-3 py-2.5 text-sm text-white placeholder-gray-600 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20';

export default function Storage() {
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [mounts, setMounts] = useState<Mount[]>([]);
  const [editing, setEditing] = useState<Mount | null>(null);
  const [form, setForm] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);

  const load = async () => {
    const [driverResult, mountResult] = await Promise.all([api.getStorageDrivers(), api.getMounts()]);
    setDrivers(driverResult.drivers); setMounts(mountResult.mounts);
  };
  useEffect(() => { load().catch((error) => setNotice({ ok: false, text: error.message })); }, []);

  const driver = useMemo(() => drivers.find((item) => item.key === form?.driver), [drivers, form?.driver]);
  const openCreate = () => {
    const first = drivers[0]; if (!first) return;
    setEditing(null); setForm({ name: '', mount_path: '/', driver: first.key, enabled: true, default: mounts.length === 0, config: Object.fromEntries(first.fields.map((field) => [field.key, field.default ?? ''])) }); setNotice(null);
  };
  const openEdit = async (mount: Mount) => {
    setBusy(true); setNotice(null);
    try {
      const detail = await api.getMount(mount.id);
      setEditing(detail); setForm({ ...detail, config: { ...detail.config } });
    } catch (error: any) { setNotice({ ok: false, text: error.message }); }
    finally { setBusy(false); }
  };
  const set = (key: string, value: any) => setForm((current: any) => ({ ...current, [key]: value }));
  const setConfig = (key: string, value: any) => setForm((current: any) => ({ ...current, config: { ...current.config, [key]: value } }));
  const changeDriver = (key: string) => { const next = drivers.find((item) => item.key === key); setForm((current: any) => ({ ...current, driver: key, config: Object.fromEntries((next?.fields || []).map((field) => [field.key, field.default ?? ''])) })); };

  const save = async () => {
    setBusy(true); setNotice(null);
    try {
      if (editing) await api.updateMount(editing.id, form); else await api.createMount(form);
      await load(); setForm(null); setEditing(null); setNotice({ ok: true, text: editing ? '挂载点已更新。' : '挂载点已创建。' });
    } catch (error: any) { setNotice({ ok: false, text: error.message }); } finally { setBusy(false); }
  };
  const test = async (mount: Mount) => {
    setBusy(true); setNotice(null);
    try { await api.testMount(mount.id); setNotice({ ok: true, text: `${mount.name} 连接正常。` }); }
    catch (error: any) { setNotice({ ok: false, text: `${mount.name}：${error.message}` }); }
    finally { setBusy(false); }
  };
  const remove = async (mount: Mount) => {
    if (!confirm(`删除挂载点“${mount.name}”？不会删除云端文件。`)) return;
    try { await api.deleteMount(mount.id); await load(); setNotice({ ok: true, text: '挂载点已删除。' }); }
    catch (error: any) { setNotice({ ok: false, text: error.message }); }
  };

  return <div className="mx-auto max-w-6xl space-y-6">
    <header className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div><h1 className="text-2xl font-bold text-white">存储挂载</h1><p className="mt-1 text-sm text-gray-500">每个挂载点拥有独立驱动、凭据和目标路径，归档任务可按需选择。</p></div>
      <button onClick={openCreate} className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white hover:bg-blue-500"><Plus size={17}/>新增挂载点</button>
    </header>
    {notice && <div role="status" className={`rounded-lg border p-3 text-sm ${notice.ok ? 'border-emerald-800 bg-emerald-950/30 text-emerald-300' : 'border-red-800 bg-red-950/30 text-red-300'}`}>{notice.text}</div>}

    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="space-y-3">
        {mounts.length === 0 && <div className="rounded-lg border border-dashed border-gray-700 p-10 text-center text-sm text-gray-500">还没有挂载点。</div>}
        {mounts.map((mount) => <article key={mount.id} className="rounded-lg border border-gray-800 bg-gray-900 p-4">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-gray-800 text-blue-300"><Database size={20}/></span>
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="font-semibold text-white">{mount.name}</h2>{mount.default && <span className="rounded bg-blue-500/15 px-2 py-0.5 text-xs text-blue-300">默认</span>}<span className={`rounded px-2 py-0.5 text-xs ${mount.enabled ? 'bg-emerald-500/15 text-emerald-300' : 'bg-gray-800 text-gray-500'}`}>{mount.enabled ? '已启用' : '已停用'}</span></div><p className="mt-1 break-all text-xs text-gray-500">{drivers.find((item) => item.key === mount.driver)?.name || mount.driver} · {mount.mount_path}</p></div>
          </div>
          <div className="mt-4 flex flex-wrap justify-end gap-2"><button disabled={busy} onClick={() => test(mount)} className="inline-flex items-center gap-1.5 rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 hover:bg-gray-800"><CheckCircle2 size={15}/>测试连接</button><button onClick={() => openEdit(mount)} className="rounded-lg border border-gray-700 px-3 py-2 text-xs text-gray-300 hover:bg-gray-800">编辑</button><button onClick={() => remove(mount)} disabled={mount.default} title={mount.default ? '请先设置其他默认挂载点' : '删除'} className="grid h-8 w-8 place-items-center rounded-lg text-gray-500 hover:bg-red-950 hover:text-red-400 disabled:opacity-30"><Trash2 size={16}/></button></div>
        </article>)}
      </section>

      <aside className="rounded-lg border border-gray-800 bg-gray-900 p-4">
        <h2 className="flex items-center gap-2 font-semibold text-white"><Server size={18}/>{drivers.length} 种 OpenList 驱动</h2>{drivers.length === 0 ? <p className="mt-4 text-sm leading-6 text-gray-500">尚未连接 OpenList。配置 OpenList 管理连接后，这里会实时显示其全部驱动。</p> : <div className="mt-4 max-h-[36rem] space-y-2 overflow-y-auto pr-1">{drivers.map((item) => <button key={item.key} onClick={() => { if (!form) openCreate(); setTimeout(() => changeDriver(item.key), 0); }} className="w-full rounded-lg border border-gray-800 bg-gray-950/30 p-3 text-left hover:border-gray-700"><strong className="block text-sm text-gray-200">{item.name}</strong></button>)}</div>}
      </aside>
    </div>

    {form && <div className="fixed inset-0 z-[60] grid place-items-center overflow-y-auto bg-black/70 p-3 sm:p-6"><div role="dialog" aria-modal="true" aria-label={editing ? '编辑挂载点' : '新增挂载点'} className="my-auto w-full max-w-2xl rounded-lg border border-gray-700 bg-gray-900 shadow-2xl">
      <header className="flex items-center justify-between border-b border-gray-800 p-4 sm:p-5"><div><h2 className="font-semibold text-white">{editing ? '编辑挂载点' : '新增挂载点'}</h2><p className="mt-1 text-xs text-gray-500">选择驱动并填写连接信息。</p></div><button aria-label="关闭" onClick={() => setForm(null)} className="grid h-9 w-9 place-items-center rounded-lg text-gray-500 hover:bg-gray-800 hover:text-white"><X size={18}/></button></header>
      <div className="max-h-[70vh] space-y-4 overflow-y-auto p-4 sm:p-5">
        <div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-1.5 text-sm text-gray-400"><span>名称</span><input className={inputClass} value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="主存储"/></label><label className="grid gap-1.5 text-sm text-gray-400"><span>挂载路径</span><input className={inputClass} value={form.mount_path} onChange={(e) => set('mount_path', e.target.value)} placeholder="/archive"/></label></div>
        <label className="grid gap-1.5 text-sm text-gray-400"><span>存储驱动</span><select disabled={Boolean(editing)} className={`${inputClass} disabled:cursor-not-allowed disabled:opacity-60`} value={form.driver} onChange={(e) => changeDriver(e.target.value)}>{drivers.map((item) => <option key={item.key} value={item.key}>{item.name}</option>)}</select></label>
        <div className="grid gap-4 sm:grid-cols-2">{driver?.fields.map((field) => <label key={field.key} className={`grid gap-1.5 text-sm text-gray-400 ${field.type === 'textarea' ? 'sm:col-span-2' : ''}`}><span>{field.label}{field.required ? ' *' : ''}</span>{field.type === 'boolean' ? <input type="checkbox" checked={form.config[field.key] === true || form.config[field.key] === 'true'} onChange={(e) => setConfig(field.key, e.target.checked)} className="h-5 w-5 accent-blue-500"/> : field.type === 'select' ? <select className={inputClass} value={form.config[field.key] ?? ''} onChange={(e) => setConfig(field.key, e.target.value)}>{field.options?.map((option) => <option key={option} value={option}>{option}</option>)}</select> : field.type === 'textarea' ? <textarea rows={5} className={`${inputClass} font-mono text-xs`} value={form.config[field.key] || ''} onChange={(e) => setConfig(field.key, e.target.value)} placeholder={editing && field.secret && form.secret_fields_set?.includes(field.key) ? '已保存；留空保持不变' : field.placeholder}/> : <input className={inputClass} type={field.secret ? 'password' : field.type === 'number' ? 'number' : 'text'} value={form.config[field.key] ?? ''} onChange={(e) => setConfig(field.key, e.target.value)} placeholder={editing && field.secret && form.secret_fields_set?.includes(field.key) ? '已保存；留空保持不变' : field.placeholder}/>} {field.help && <small className="text-xs leading-5 text-gray-600">{field.help}</small>}</label>)}</div>
        <div className="flex flex-wrap gap-5 border-t border-gray-800 pt-4"><label className="flex items-center gap-2 text-sm text-gray-300"><input type="checkbox" checked={form.enabled} onChange={(e) => set('enabled', e.target.checked)} className="h-4 w-4 accent-blue-500"/>启用</label><label className="flex items-center gap-2 text-sm text-gray-300"><input type="checkbox" checked={form.default} onChange={(e) => set('default', e.target.checked)} className="h-4 w-4 accent-blue-500"/>设为默认目标</label></div>
      </div>
      <footer className="flex justify-end gap-3 border-t border-gray-800 p-4"><button onClick={() => setForm(null)} className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300">取消</button><button disabled={busy} onClick={save} className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"><Save size={16}/>{busy ? '保存中…' : '保存挂载点'}</button></footer>
    </div></div>}
  </div>;
}
