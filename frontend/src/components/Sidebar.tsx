import { motion } from 'motion/react';
import { cn } from '../utils/cn';
import type { Page } from '../App';
import { Icon } from './Icon';

interface SidebarProps {
  isOpen: boolean;
  currentPage: Page;
  onNavigate: (page: Page) => void;
}

export function Sidebar({ isOpen, currentPage, onNavigate }: SidebarProps) {
  const navItems = [
    { id: 'dashboard', label: '仪表盘', icon: 'dashboard' },
    { id: 'camera', label: '实时监控', icon: 'videocam' },
    { id: 'inventory', label: '库存管理', icon: 'inventory_2' },
    { id: 'reports', label: '统计报表', icon: 'bar_chart' },
    { id: 'settings', label: '系统设置', icon: 'settings' },
  ] as const;

  return (
    <motion.aside
      initial={false}
      animate={{ width: isOpen ? 256 : 80 }}
      className="bg-[#f8f9fa] border-r border-[#dadce0] text-[#202124] flex flex-col relative z-20 shrink-0 overflow-hidden"
    >
      <div className="h-16 flex items-center justify-center px-4 shrink-0">
        <div className="flex items-center gap-3 font-medium text-lg w-full">
          <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0">
            <Icon name="camera" className="text-[#1a73e8]" size={28} filled />
          </div>
          <motion.span 
            animate={{ opacity: isOpen ? 1 : 0, display: isOpen ? 'block' : 'none' }}
            initial={false}
            className="truncate text-[#202124] tracking-tight"
          >
            Cam
          </motion.span>
        </div>
      </div>

      <nav className="flex-1 py-4 flex flex-col gap-1 px-3 mt-2 overflow-y-auto w-full">
        {navItems.map((item) => {
          const isActive = currentPage === item.id;
          return (
            <motion.button
              whileTap={{ scale: 0.97 }}
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={cn(
                "flex items-center rounded-full transition-colors group relative overflow-hidden h-12 w-full",
                isOpen ? "px-4 justify-start" : "px-0 justify-center",
                isActive 
                  ? "bg-[#c2e7ff] text-[#001d35]" 
                  : "hover:bg-[#e8eaed] text-[#444746]"
              )}
              title={!isOpen ? item.label : undefined}
            >
              <Icon 
                name={item.icon} 
                filled={isActive}
                size={24}
                className={cn("shrink-0 relative z-10", isActive ? "text-[#001d35]" : "text-[#444746] group-hover:text-[#1f1f1f]")} 
              />
              <motion.span 
                animate={{ opacity: isOpen ? 1 : 0, width: isOpen ? 'auto' : 0 }}
                className={cn(
                  "font-medium tracking-wide whitespace-nowrap ml-3 relative z-10",
                  isActive ? "text-[#001d35]" : "text-[#444746]"
                )}
              >
                {item.label}
              </motion.span>
            </motion.button>
          );
        })}
      </nav>

      <div className="p-4 shrink-0">
        <div className={cn("flex items-center", isOpen ? "gap-3" : "justify-center")}>
          <div className="w-10 h-10 rounded-full bg-[#1a73e8] flex items-center justify-center shrink-0">
            <span className="text-sm font-medium text-white">AD</span>
          </div>
          {isOpen && (
            <div className="flex-1 overflow-hidden">
              <p className="text-sm font-medium text-[#202124] truncate">管理员</p>
              <p className="text-xs text-[#5f6368] truncate">Cam Workspace</p>
            </div>
          )}
        </div>
      </div>
    </motion.aside>
  );
}
