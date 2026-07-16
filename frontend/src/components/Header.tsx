import { motion } from 'motion/react';
import { Icon } from './Icon';

interface HeaderProps {
  onMenuToggle: () => void;
  onLogout: () => void;
}

export function Header({ onMenuToggle, onLogout }: HeaderProps) {
  return (
    <header className="h-16 bg-white border-b border-[#dadce0] flex items-center justify-between px-4 md:px-6 z-10">
      <div className="flex items-center gap-4">
        <motion.button 
          whileTap={{ scale: 0.9 }}
          onClick={onMenuToggle}
          className="w-12 h-12 flex justify-center items-center -ml-2 text-[#5f6368] hover:bg-[#f1f3f4] rounded-full transition-colors"
        >
          <Icon name="menu" size={24} />
        </motion.button>
        
        <div className="hidden md:flex items-center gap-2 bg-[#f1f3f4] px-4 py-2 rounded-full w-96 focus-within:bg-white focus-within:shadow-[0_1px_1px_0_rgba(65,69,73,0.3),0_1px_3px_1px_rgba(65,69,73,0.15)] transition-all">
          <Icon name="search" size={20} className="text-[#5f6368]" />
          <input 
            type="text" 
            placeholder="Search items, events, or reports..." 
            className="bg-transparent border-none outline-none text-[15px] w-full text-[#202124] placeholder:text-[#5f6368]"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <motion.button 
          whileTap={{ scale: 0.9 }}
          className="relative w-10 h-10 flex justify-center items-center text-[#5f6368] hover:bg-[#f1f3f4] rounded-full transition-colors"
        >
          <Icon name="notifications" size={24} />
          <span className="absolute top-2 right-2 w-2 h-2 bg-[#ea4335] rounded-full border-2 border-white"></span>
        </motion.button>
        
        <motion.button 
          whileTap={{ scale: 0.95 }}
          onClick={onLogout}
          className="flex items-center justify-center ml-2 w-10 h-10 text-[#5f6368] hover:bg-[#fce8e6] hover:text-[#d93025] rounded-full transition-colors"
          title="退出登录"
        >
          <Icon name="logout" size={24} />
        </motion.button>
      </div>
    </header>
  );
}
