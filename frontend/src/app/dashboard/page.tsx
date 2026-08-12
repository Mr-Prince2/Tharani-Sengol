'use client';

import { motion } from 'framer-motion';
import { Download } from 'lucide-react';
import { useEffect, useState } from 'react';

const MapPlaceholder = () => (
  <div className="w-full h-full min-h-[400px] bg-[#111728] rounded-xl flex flex-col items-center justify-center border border-[#ffffff14] relative overflow-hidden">
    <div className="w-12 h-12 border-4 border-sky-500 border-t-transparent rounded-full animate-spin mb-4"></div>
    <p className="text-slate-400 font-medium text-sm">Initializing Geospatial Telemetry Engine...</p>
  </div>
);

const SkeletonKPI = () => (
  <div className="h-10 w-16 bg-[#1c253d] rounded animate-pulse mt-1"></div>
);

const SkeletonAlert = () => (
  <div className="p-3 bg-[#111728] rounded-lg border border-[#ffffff14] space-y-2 animate-pulse">
    <div className="h-4 w-20 bg-[#1c253d] rounded"></div>
    <div className="h-3 w-full bg-[#1c253d] rounded"></div>
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
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const stats = data?.state_metrics || {};
  const sys = data?.system_metrics || {};
  const prediction = data?.prediction_metrics || {};

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className="w-full"
    >
      <div className="dashboard-bento">
        {/* Top Action Bar */}
        <section className="bento-card bento-actions">
          <div className="flex items-center gap-4">
            <strong className="text-[var(--text-primary)]">Exports:</strong>
            <button className="flex items-center gap-2 text-sm text-sky-400 hover:text-white transition-colors"><Download size={14}/> Alerts</button>
            <button className="flex items-center gap-2 text-sm text-sky-400 hover:text-white transition-colors"><Download size={14}/> Violations</button>
            <button className="flex items-center gap-2 text-sm text-sky-400 hover:text-white transition-colors"><Download size={14}/> Trips</button>
          </div>
        </section>

        {/* Unified KPIs Row */}
        <section className="bento-card bento-kpis">
          <div className="kpi-grid">
            <div className="kpi-item"><span>Active Vehicles</span>{loading ? <SkeletonKPI /> : <strong>{stats.active_trucks || 0}</strong>}</div>
            <div className="kpi-item"><span>Total Trips</span>{loading ? <SkeletonKPI /> : <strong>{sys.total_trips || 0}</strong>}</div>
            <div className="kpi-item"><span>Dangerous</span>{loading ? <SkeletonKPI /> : <strong className="text-rose-400">{sys.danger_count || 0}</strong>}</div>
            <div className="kpi-item"><span>Suspicious</span>{loading ? <SkeletonKPI /> : <strong className="text-amber-400">{sys.suspicious_count || 0}</strong>}</div>
            <div className="kpi-item"><span>Avg Risk</span>{loading ? <SkeletonKPI /> : <strong>{(stats.avg_risk || 0).toFixed(1)}</strong>}</div>
            <div className="kpi-item"><span>Avg Threat</span>{loading ? <SkeletonKPI /> : <strong>{(stats.avg_threat || 0).toFixed(1)}</strong>}</div>
            <div className="kpi-item"><span>Configured Mines</span>{loading ? <SkeletonKPI /> : <strong>{stats.configured_mines || 0}</strong>}</div>
            <div className="kpi-item"><span>Overloads</span>{loading ? <SkeletonKPI /> : <strong>{stats.overloads || 0}</strong>}</div>
          </div>
        </section>

        {/* Main View: Map & Alerts */}
        <section className="bento-card bento-map p-0 overflow-hidden">
          <div className="p-6 pb-2">
            <h2>Live Operations Map</h2>
          </div>
          <div className="flex-1 p-2">
             <MapPlaceholder />
          </div>
        </section>
        
        <section className="bento-card bento-alerts flex flex-col">
          <h2>Live Alerts</h2>
          <div className="flex-1 overflow-y-auto space-y-3">
             {loading ? (
               <>
                 <SkeletonAlert />
                 <SkeletonAlert />
                 <SkeletonAlert />
               </>
             ) : (
               data?.latest_alerts?.slice(0, 5).map((alert: any, i: number) => (
                 <motion.div 
                   initial={{ opacity: 0, x: 20 }}
                   animate={{ opacity: 1, x: 0 }}
                   transition={{ delay: i * 0.1 }}
                   key={i} 
                   className="p-3 bg-[#111728] rounded-lg border border-[#ffffff14]"
                 >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-bold text-sky-400">
                        {alert.risk_level}
                      </span>
                    </div>
                    <p className="text-sm text-slate-300">{alert.event_summary || 'Vehicle threshold alert registered.'}</p>
                 </motion.div>
               )) || <p className="text-sm text-slate-500">Waiting for alerts...</p>
             )}
          </div>
        </section>

        {/* AI Prediction Stack */}
        <section className="bento-card bento-ai">
          <h2>AI Prediction Stack</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="bg-[#111728] p-4 rounded-xl border border-[#ffffff14]">
              <h3 className="text-lg font-bold mb-3">Classification</h3>
              <div className="kpi-grid">
                <div className="kpi-item"><span>High Prob</span><strong>{prediction.class_high || 0}</strong></div>
                <div className="kpi-item"><span>Avg Prob</span><strong>{(prediction.class_avg_prob || 0).toFixed(1)}%</strong></div>
              </div>
            </div>
            <div className="bg-[#111728] p-4 rounded-xl border border-[#ffffff14]">
              <h3 className="text-lg font-bold mb-3">Regression</h3>
              <div className="kpi-grid">
                <div className="kpi-item"><span>Locked</span><strong>{prediction.reg_locked || 0}</strong></div>
                <div className="kpi-item"><span>Avg Wgt</span><strong>{(prediction.reg_avg_weight || 0).toFixed(1)}t</strong></div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </motion.div>
  );
}
