'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import { Activity, LayoutDashboard, Truck, BarChart3, ShieldAlert, Cpu, UserCog, Menu } from 'lucide-react';
import { useState, useEffect } from 'react';

const navItems = [
  { name: 'Overview', href: '/', icon: Activity },
  { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
  { name: 'Vehicles', href: '/vehicles', icon: Truck },
  { name: 'Alerts', href: '/alerts', icon: ShieldAlert },
  { name: 'Analytics', href: '/analytics', icon: BarChart3 },
  { name: 'AI Prediction', href: '/ai-prediction', icon: Cpu },
  { name: 'Admin', href: '/admin', icon: UserCog },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkScreen = () => setIsMobile(window.innerWidth < 768);
    checkScreen();
    window.addEventListener('resize', checkScreen);
    return () => window.removeEventListener('resize', checkScreen);
  }, []);

  return (
    <>
      <button 
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-[#141b2d] rounded text-white border border-[#ffffff14]"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Menu size={24} />
      </button>

      <motion.aside 
        initial={{ x: -300 }}
        animate={{ x: (isOpen || !isMobile) ? 0 : -300 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="fixed md:sticky top-0 h-screen w-64 bg-[#0f1424] border-r border-[#ffffff14] flex flex-col z-40"
      >
        <div className="p-6 border-b border-[#ffffff14] flex flex-col items-center">
          <div className="w-12 h-12 bg-gradient-to-r from-sky-600 to-blue-600 rounded-xl flex items-center justify-center mb-3 shadow-[0_0_18px_rgba(56,189,248,0.35)]">
            <ShieldAlert size={28} className="text-white" />
          </div>
          <h1 className="text-xl font-bold text-white tracking-wide">Tharani Sengol</h1>
        </div>

        <nav className="flex-1 p-4 overflow-y-auto space-y-2">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            
            return (
              <Link key={item.name} href={item.href} onClick={() => setIsOpen(false)}>
                <div className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${isActive ? 'bg-gradient-to-r from-sky-600 to-blue-600 text-white shadow-md' : 'text-slate-400 hover:bg-[#1c253d] hover:text-white'}`}>
                  <Icon size={20} />
                  <span className="font-medium">{item.name}</span>
                </div>
              </Link>
            );
          })}
        </nav>
      </motion.aside>

      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 md:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}
    </>
  );
}
