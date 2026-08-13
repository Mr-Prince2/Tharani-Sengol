'use client';

import { motion } from 'framer-motion';
import { Download, Shield, Radio, Activity, AlertTriangle, Cpu } from 'lucide-react';
import { useEffect, useState } from 'react';

const MapPlaceholder = () => (
  <div className="w-full h-full min-h-[420px] bg-[#09090a]/90 rounded-xl flex flex-col items-center justify-center border border-white/20 relative overflow-hidden group">
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.06),transparent_70%)] pointer-events-none" />
    <div className="w-14 h-14 border-4 border-white border-t-transparent rounded-full animate-spin mb-4 shadow-[0_0_20px_rgba(255,255,255,0.3)]" />
    <p className="text-white font-mono font-semibold text-sm tracking-wider uppercase">Initializing Satellite Telemetry GIS Engine...</p>
    <span className="text-xs text-zinc-400 font-mono mt-1">TRICHY SECTOR • LIVE SATELLITE VECTOR HUD</span>
  </div>
);

const SkeletonKPI = () => (
  <div className="h-8 w-16 bg-zinc-900 rounded animate-pulse mt-1 border border-white/10"></div>
);

const SkeletonAlert = () => (
  <div className="p-3 bg-[#121214] rounded-lg border border-white/20 space-y-2 animate-pulse">
    <div className="h-4 w-20 bg-zinc-800 rounded"></div>
    <div className="h-3 w-full bg-zinc-900 rounded"></div>
  </div>
);

export default function Dashboard() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/control-state');
        if (res.ok) {
          const json = await res.json();
          setData(json);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
    const interval = setInterval(fetchData, 4000);
    return () => clearInterval(interval);
  }, []);

  const stats = data?.state_metrics || {};
  const sys = data?.system_metrics || {};
  const prediction = data?.prediction_metrics || {};

  return (
    <motion.div 
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="w-full space-y-6 font-sans"
    >
      {/* Government Tactical Top Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-[#121214]/90 border border-white/20 rounded-xl backdrop-blur-md shadow-[0_0_20px_rgba(255,255,255,0.05)]">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-white/10 border border-white/30 rounded-lg">
            <Radio className="text-white animate-pulse" size={20} />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white tracking-wide uppercase font-sans flex items-center gap-2">
              National Intelligence HUD
              <span className="text-[10px] font-mono font-bold bg-white text-black px-2 py-0.5 rounded">LIVE TELEMETRY</span>
            </h2>
            <p className="text-xs text-zinc-400">Department of Geology & Mining • Automated Surveillance Division</p>
          </div>
        </div>

        <div className="flex items-center gap-2 font-mono text-xs">
          <strong className="text-zinc-400 mr-1">EXPORTS:</strong>
          <button className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-black hover:bg-zinc-200 border border-white rounded-md transition-all font-bold">
            <Download size={13}/> Alerts
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-black hover:bg-zinc-200 border border-white rounded-md transition-all font-bold">
            <Download size={13}/> Violations
          </button>
          <button className="flex items-center gap-1.5 px-3 py-1.5 bg-white text-black hover:bg-zinc-200 border border-white rounded-md transition-all font-bold">
            <Download size={13}/> Trips
          </button>
        </div>
      </div>

      {/* Unified Tactical KPIs Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
        {[
          { label: 'Active Fleet', val: stats.active_trucks || 0, color: 'text-white' },
          { label: 'Total Trips', val: sys.total_trips || 0, color: 'text-zinc-300' },
          { label: 'Dangerous', val: sys.danger_count || 0, color: 'text-white' },
          { label: 'Suspicious', val: sys.suspicious_count || 0, color: 'text-zinc-300' },
          { label: 'Avg Risk', val: (stats.avg_risk || 0).toFixed(1), color: 'text-white' },
          { label: 'Avg Threat', val: (stats.avg_threat || 0).toFixed(1), color: 'text-zinc-300' },
          { label: 'Active Mines', val: stats.configured_mines || 0, color: 'text-white' },
          { label: 'Overloads', val: stats.overloads || 0, color: 'text-zinc-300' },
        ].map((kpi, idx) => (
          <div key={idx} className="p-3 bg-[#121214]/85 border border-white/20 rounded-xl backdrop-blur-md hover:border-white/50 transition-all hover:shadow-[0_0_15px_rgba(255,255,255,0.1)]">
            <span className="text-[10px] font-mono text-zinc-400 uppercase tracking-wider block">{kpi.label}</span>
            {loading ? <SkeletonKPI /> : <strong className={`text-xl font-bold font-mono ${kpi.color} block mt-0.5`}>{kpi.val}</strong>}
          </div>
        ))}
      </div>

      {/* Main Grid: GIS Telemetry Map & Real-time Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-[#121214]/90 border border-white/20 rounded-xl p-4 flex flex-col backdrop-blur-md">
          <div className="flex items-center justify-between mb-3 px-1">
            <h3 className="text-base font-bold text-white uppercase tracking-wider font-sans flex items-center gap-2">
              <Activity size={18} className="text-white" />
              Live Operations Map & GIS Surveillance
            </h3>
            <span className="text-[11px] font-mono text-black bg-white border border-white px-2 py-0.5 rounded font-bold">GPS STREAM ONLINE</span>
          </div>
          <div className="flex-1">
            <MapPlaceholder />
          </div>
        </div>

        <div className="bg-[#121214]/90 border border-white/20 rounded-xl p-4 flex flex-col backdrop-blur-md">
          <div className="flex items-center justify-between mb-3 px-1">
            <h3 className="text-base font-bold text-white uppercase tracking-wider font-sans flex items-center gap-2">
              <AlertTriangle size={18} className="text-white" />
              Live Enforcement Alerts
            </h3>
            <span className="text-[10px] font-mono text-zinc-400">REALTIME</span>
          </div>
          <div className="flex-1 overflow-y-auto space-y-2.5 max-h-[420px] pr-1">
            {loading ? (
              <>
                <SkeletonAlert />
                <SkeletonAlert />
                <SkeletonAlert />
              </>
            ) : (
              data?.latest_alerts?.slice(0, 6).map((alert: any, i: number) => (
                <motion.div 
                  initial={{ opacity: 0, x: 15 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.08 }}
                  key={i} 
                  className="p-3 bg-[#09090a] rounded-lg border border-white/20 hover:border-white/40 transition-all"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                      alert.risk_level === 'CRITICAL' || alert.risk_level === 'HIGH'
                        ? 'bg-white text-black border-white'
                        : alert.risk_level === 'WARNING'
                        ? 'bg-zinc-800 text-white border-zinc-600'
                        : 'bg-zinc-900 text-zinc-300 border-zinc-700'
                    }`}>
                      [{alert.risk_level || 'ALERT'}]
                    </span>
                    <span className="text-[10px] font-mono text-zinc-400">LIVE SENSOR</span>
                  </div>
                  <p className="text-xs text-zinc-300 font-sans leading-relaxed">{alert.event_summary || 'Vehicle threshold alert registered.'}</p>
                </motion.div>
              )) || <p className="text-xs text-zinc-400 font-mono p-4 text-center">Waiting for telemetry alerts...</p>
            )}
          </div>
        </div>
      </div>

      {/* AI Telemetry & Neural Axle Weight Stack */}
      <div className="bg-[#121214]/90 border border-white/20 rounded-xl p-5 backdrop-blur-md">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold text-white uppercase tracking-wider font-sans flex items-center gap-2">
            <Cpu size={18} className="text-white" />
            Neural AI Prediction & Axle Weight Telemetry Stack
          </h3>
          <span className="text-xs font-mono text-zinc-400">ML INFERENCE ENGINE ACTIVE</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-[#09090a] p-4 rounded-xl border border-white/20">
            <h4 className="text-xs font-mono font-bold text-white uppercase tracking-wider mb-3">Vehicle Classification Neural Model</h4>
            <div className="grid grid-cols-2 gap-3 font-mono">
              <div className="p-2.5 bg-[#121214] rounded-lg border border-white/10">
                <span className="text-[10px] text-zinc-400 block">High Probability</span>
                <strong className="text-lg text-white">{prediction.class_high || 0}</strong>
              </div>
              <div className="p-2.5 bg-[#121214] rounded-lg border border-white/10">
                <span className="text-[10px] text-zinc-400 block">Avg Confidence</span>
                <strong className="text-lg text-zinc-200">{(prediction.class_avg_prob || 0).toFixed(1)}%</strong>
              </div>
            </div>
          </div>
          <div className="bg-[#09090a] p-4 rounded-xl border border-white/20">
            <h4 className="text-xs font-mono font-bold text-white uppercase tracking-wider mb-3">Dynamic Axle Weight Regression Model</h4>
            <div className="grid grid-cols-2 gap-3 font-mono">
              <div className="p-2.5 bg-[#121214] rounded-lg border border-white/10">
                <span className="text-[10px] text-slate-400 block">Weight Lock Verified</span>
                <strong className="text-lg text-white">{prediction.reg_locked || 0}</strong>
              </div>
              <div className="p-2.5 bg-[#121214] rounded-lg border border-white/10">
                <span className="text-[10px] text-slate-400 block">Avg Estimated Weight</span>
                <strong className="text-lg text-zinc-200">{(prediction.reg_avg_weight || 0).toFixed(1)} T</strong>
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
