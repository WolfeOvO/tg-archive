import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';

const navItems = [
  { path: '/', label: '仪表盘', icon: '📊' },
  { path: '/tasks', label: '归档任务', icon: '📋' },
  { path: '/logs', label: '操作日志', icon: '📝' },
  { path: '/settings', label: '设置', icon: '⚙️' },
];

export default function Layout({ children }: { children: React.ReactNode }) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-gray-950 flex">
      {/* Sidebar */}
      <aside className="hidden w-64 shrink-0 bg-gray-900 border-r border-gray-800 md:flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-gray-800">
          <div className="flex items-center gap-3">
            <span className="text-2xl">📦</span>
            <div>
              <h1 className="text-lg font-bold text-white">TG Archive</h1>
              <p className="text-xs text-gray-500">Telegram 频道归档</p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-600/30'
                    : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                }`
              }
            >
              <span className="text-base">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="p-4 border-t border-gray-800">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-gray-500 hover:bg-gray-800 hover:text-red-400 transition-colors"
          >
            <span>🚪</span>
            退出登录
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="min-w-0 flex-1 overflow-auto pb-20 md:pb-0">
        <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto">
          {children}
        </div>
      </main>

      <nav aria-label="手机导航" className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t border-gray-800 bg-gray-900/95 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `flex min-w-0 flex-col items-center gap-1 px-1 py-2 text-xs ${isActive ? 'text-blue-400' : 'text-gray-500'}`}
          >
            <span aria-hidden="true" className="text-base">{item.icon}</span>
            <span className="truncate">{item.label}</span>
          </NavLink>
        ))}
        <button onClick={handleLogout} className="flex min-w-0 flex-col items-center gap-1 px-1 py-2 text-xs text-gray-500 hover:text-red-400">
          <span aria-hidden="true" className="text-base">🚪</span>
          <span className="truncate">退出</span>
        </button>
      </nav>
    </div>
  );
}
