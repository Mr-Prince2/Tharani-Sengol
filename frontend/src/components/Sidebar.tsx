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
        className="md:hidden fixed top-4 left-4 z-50 p-2 bg-[#070d1e] rounded-lg text-cyan-400 border border-cyan-500/30 shadow-[0_0_12px_rgba(0,240,255,0.2)]"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Menu size={22} />
      </button>

      <motion.aside 
        initial={{ x: -300 }}
        animate={{ x: (isOpen || !isMobile) ? 0 : -300 }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        className="fixed md:sticky top-0 h-screen w-64 bg-[#070d1e]/95 backdrop-blur-xl border-r border-cyan-500/20 flex flex-col z-40"
      >
        {/* Header / Seal Branding */}
        <div className="p-5 border-b border-cyan-500/20 flex flex-col items-center text-center relative overflow-hidden">
          <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/10 rounded-full blur-2xl pointer-events-none" />
          <div className="w-12 h-12 bg-gradient-to-br from-cyan-500 to-blue-700 rounded-xl flex items-center justify-center mb-2.5 shadow-[0_0_20px_rgba(0,240,255,0.4)] border border-cyan-400/40">
            <Shield size={26} className="text-white" />
          </div>
          <h1 className="text-lg font-extrabold text-white tracking-wider uppercase font-sans">Tharani Sengol</h1>
          <span className="text-[10px] font-mono text-cyan-400 tracking-widest uppercase mt-0.5 px-2 py-0.5 bg-cyan-950/60 border border-cyan-500/30 rounded">
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
                    ? 'bg-gradient-to-r from-cyan-500/20 to-blue-600/20 border border-cyan-400/40 text-cyan-300 shadow-[0_0_15px_rgba(0,240,255,0.15)] font-semibold' 
                    : 'text-slate-400 hover:bg-[#0f1936] hover:text-slate-200'
                }`}>
                  <Icon size={18} className={isActive ? 'text-cyan-400 drop-shadow-[0_0_6px_rgba(0,240,255,0.6)]' : 'text-slate-400'} />
                  <span>{item.name}</span>
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Footer Status Badge */}
        <div className="p-3.5 border-t border-cyan-500/20 bg-[#050a17]/80 text-[11px] font-mono text-slate-400 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-[0_0_8px_#10b981]" />
            <span>SAT-LINK OK</span>
          </div>
          <span className="text-cyan-400 font-bold">TN-GOV</span>
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
