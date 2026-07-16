/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { Suspense, lazy, startTransition, useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { Login } from './pages/Login';
import { isAuthenticated as hasStoredSession, logout } from './utils/auth';

export type Page = 'dashboard' | 'camera' | 'inventory' | 'reports' | 'settings';

const Dashboard = lazy(() =>
  import('./pages/Dashboard').then((module) => ({ default: module.Dashboard }))
);
const LiveCameraDemo = lazy(() =>
  import('./pages/LiveCameraDemo').then((module) => ({ default: module.LiveCameraDemo }))
);
const InventoryManagement = lazy(() =>
  import('./pages/InventoryManagement').then((module) => ({
    default: module.InventoryManagement,
  }))
);
const Reports = lazy(() =>
  import('./pages/Reports').then((module) => ({ default: module.Reports }))
);
const SettingsManagement = lazy(() =>
  import('./pages/SettingsManagement').then((module) => ({
    default: module.SettingsManagement,
  }))
);

function PageLoadingFallback() {
  return (
    <div className="flex min-h-[320px] items-center justify-center rounded-[28px] border border-[#dadce0] bg-white px-6 text-sm text-slate-500 shadow-sm">
      页面内容加载中...
    </div>
  );
}

export default function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(hasStoredSession());
  const [currentPage, setCurrentPage] = useState<Page>('dashboard');
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [hasOpenedCameraPage, setHasOpenedCameraPage] = useState(false);

  const handleNavigate = (page: Page) => {
    startTransition(() => {
      if (page === 'camera') {
        setHasOpenedCameraPage(true);
      }
      setCurrentPage(page);
    });
  };

  if (!isAuthenticated) {
    return <Login onLogin={() => setIsAuthenticated(true)} />;
  }

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden font-sans text-slate-900">
      <Sidebar 
        isOpen={isSidebarOpen} 
        currentPage={currentPage} 
        onNavigate={handleNavigate} 
      />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header 
          onMenuToggle={() => setIsSidebarOpen(!isSidebarOpen)} 
          onLogout={() => {
            logout();
            setIsAuthenticated(false);
          }}
        />
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
          <Suspense fallback={<PageLoadingFallback />}>
            {currentPage === 'dashboard' && <Dashboard onNavigate={handleNavigate} />}
            {hasOpenedCameraPage && (
              <div className={currentPage === 'camera' ? 'block h-full' : 'hidden'}>
                <LiveCameraDemo />
              </div>
            )}
            {currentPage === 'inventory' && <InventoryManagement />}
            {currentPage === 'reports' && <Reports />}
            {currentPage === 'settings' && <SettingsManagement />}
          </Suspense>
        </main>
      </div>
    </div>
  );
}
