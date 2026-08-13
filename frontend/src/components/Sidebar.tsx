'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { motion } from 'framer-motion';
import { Activity, LayoutDashboard, Truck, BarChart3, ShieldAlert, Cpu, UserCog, Menu, Shield } from 'lucide-react';
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
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-[#09090b] rounded-lg text-white border border-white/20 shadow-[0_0_12px_rgba(255,255,255,0.1)]"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Menu size={22} />
      </button>

      <motion.aside 
        initial={{ x: -300 }}
        animate={{ x: (isOpen || !isMobile) ? 0 : -300 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="fixed md:sticky top-0 h-screen w-64 bg-[#09090b]/95 backdrop-blur-xl border-r border-white/15 flex flex-col z-40"
      >
        {/* Header / Seal Branding */}
        <div className="p-5 border-b border-white/15 flex flex-col items-center text-center relative overflow-hidden">
          <div className="absolute top-0 right-0 w-24 h-24 bg-white/5 rounded-full blur-2xl pointer-events-none" />
          <div className="w-12 h-12 bg-white rounded-xl flex items-center justify-center mb-2.5 shadow-[0_0_20px_rgba(255,255,255,0.3)] border border-white/60">
            <Shield size={26} className="text-black" />
          </div>
          <h1 className="text-lg font-extrabold text-white tracking-wider uppercase font-sans">Tharani Sengol</h1>
          <span className="text-[10px] font-mono text-zinc-300 tracking-widest uppercase mt-0.5 px-2 py-0.5 bg-zinc-900 border border-white/20 rounded">
            LEVEL 5 CLEARANCE
          </span>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 p-3 overflow-y-auto space-y-1.5 font-sans">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            
            return (
              <Link key={item.name} href={item.href} onClick={() => setIsOpen(false)}>
                <div className={`flex items-center gap-3 px-3.5 py-2.5 rounded-lg transition-all text-sm font-medium ${
                  isActive 
                    ? 'bg-white text-black font-bold shadow-[0_0_15px_rgba(255,255,255,0.2)]' 
                    : 'text-zinc-400 hover:bg-zinc-900 hover:text-white'
                }`}>
                  <Icon size={18} className={isActive ? 'text-black' : 'text-zinc-400'} />
                  <span>{item.name}</span>
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Footer Status Badge */}
        <div className="p-3.5 border-t border-white/15 bg-[#09090b] text-[11px] font-mono text-zinc-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-white animate-pulse shadow-[0_0_8px_#ffffff]" />
            <span>SAT-LINK OK</span>
          </div>
          <span className="text-white font-bold">TN-GOV</span>
        </div>
      </motion.aside>

      {isOpen && (
        <div 
          className="fixed inset-0 bg-black/70 backdrop-blur-sm z-30 md:hidden"
          onClick={() => setIsOpen(false)}
        />
      )}
    </>
  );
}
