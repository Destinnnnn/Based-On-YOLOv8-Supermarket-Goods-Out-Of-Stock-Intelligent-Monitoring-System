import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import type { Page } from '../App';
import { authenticatedFetch } from '../utils/auth';
import { Icon } from '../components/Icon';

export function Dashboard({ onNavigate }: { onNavigate: (page: Page) => void }) {
  const [showAlerts, setShowAlerts] = useState(true);
  const [stats, setStats] = useState({
    total_items: 0,
    low_stock_count: 0,
    out_of_stock_count: 0,
    recent_alerts_count: 0,
    recent_incidents_count: 0,
  });
  const [trendData, setTrendData] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      setLoading(true);

      const statsResponse = await authenticatedFetch('/api/v1/reports/dashboard-stats');
      if (statsResponse.ok) {
        const statsData = await statsResponse.json();
        setStats(statsData);
      }

      const trendResponse = await authenticatedFetch('/api/v1/reports/stock-trend-today?hours=12');
      if (trendResponse.ok) {
        const trendData = await trendResponse.json();
        setTrendData(trendData);
      }

      const alertsResponse = await authenticatedFetch('/api/v1/reports/recent-alerts?limit=5');
      if (alertsResponse.ok) {
        const alertsData = await alertsResponse.json();
        setAlerts(alertsData.map((alert: any) => ({
          id: alert.id,
          type: alert.type,
          message: alert.message,
          time: formatTime(alert.time)
        })));
      }
    } catch (error) {
      console.error('Error loading dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return '刚刚';
    if (diffMins < 60) return `${diffMins} 分钟前`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} 小时前`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays} 天前`;
  };

  const containerVariants = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: { staggerChildren: 0.1 }
    }
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 10 },
    show: { opacity: 1, y: 0, transition: { duration: 0.4 } }
  };

  return (
    <motion.div 
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      <motion.div variants={itemVariants}>
        <h1 className="text-[22px] font-normal text-[#202124]">仪表盘总览</h1>
      </motion.div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <motion.div variants={itemVariants} className="bg-white p-6 rounded-2xl border border-[#dadce0] hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[14px] font-medium text-[#5f6368]">监控商品总数</p>
              <p className="text-[32px] text-[#202124] mt-1 font-normal">
                {loading ? '...' : stats.total_items}
              </p>
            </div>
            <div className="w-12 h-12 bg-[#e6f4ea] rounded-full flex items-center justify-center">
              <Icon name="check_circle" className="text-[#137333]" size={28} filled />
            </div>
          </div>
          <div className="mt-4 flex items-center text-[13px]">
            <span className="text-[#5f6368]">实时数据</span>
          </div>
        </motion.div>

        <motion.div variants={itemVariants} className="bg-white p-6 rounded-2xl border border-[#dadce0] hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[14px] font-medium text-[#5f6368]">低库存预警</p>
              <p className="text-[32px] text-[#202124] mt-1 font-normal">
                {loading ? '...' : stats.low_stock_count}
              </p>
            </div>
            <div className="w-12 h-12 bg-[#fef7e0] rounded-full flex items-center justify-center">
              <Icon name="warning" className="text-[#e37400]" size={28} filled />
            </div>
          </div>
          <div className="mt-4 flex items-center text-[13px]">
            <span className="text-[#e37400] font-medium">+{stats.recent_incidents_count}</span>
            <span className="text-[#5f6368] ml-2">过去一小时异常</span>
          </div>
        </motion.div>

        <motion.div variants={itemVariants} className="bg-white p-6 rounded-2xl border border-[#dadce0] hover:shadow-md transition-shadow">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[14px] font-medium text-[#5f6368]">缺货告警</p>
              <p className="text-[32px] text-[#202124] mt-1 font-normal">
                {loading ? '...' : stats.out_of_stock_count}
              </p>
            </div>
            <div className="w-12 h-12 bg-[#fce8e6] rounded-full flex items-center justify-center">
              <Icon name="inventory_2" className="text-[#d93025]" size={28} filled />
            </div>
          </div>
          <div className="mt-4 flex items-center text-[13px]">
            <span className="text-[#d93025] font-medium flex items-center">
              <Icon name="trending_down" size={16} className="mr-1" />
              {stats.out_of_stock_count > 0 ? '紧急' : '正常'}
            </span>
            <span className="text-[#5f6368] ml-2">
              {stats.out_of_stock_count > 0 ? '需立即处理' : '无需处理'}
            </span>
          </div>
        </motion.div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Chart */}
        <motion.div variants={itemVariants} className={showAlerts ? "lg:col-span-2 bg-white p-6 rounded-2xl border border-[#dadce0]" : "lg:col-span-3 bg-white p-6 rounded-2xl border border-[#dadce0]"}>
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-[16px] font-medium text-[#202124]">今日缺货频次</h2>
            <button 
              onClick={() => onNavigate('reports')}
              className="text-[14px] font-medium text-[#1a73e8] hover:bg-[#f8f9fa] px-3 py-1.5 rounded-full transition-colors flex items-center"
            >
              查看完整报表 <Icon name="arrow_forward" size={18} className="ml-1" />
            </button>
          </div>
          <div className="h-72">
            {loading ? (
              <div className="flex items-center justify-center h-full text-[#5f6368]">
                加载中...
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorOos" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ea4335" stopOpacity={0.2}/>
                    <stop offset="95%" stopColor="#ea4335" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f1f3f4" />
                <XAxis dataKey="time" axisLine={false} tickLine={false} tick={{ fill: '#5f6368', fontSize: 12 }} dy={10} />
                <YAxis axisLine={false} tickLine={false} tick={{ fill: '#5f6368', fontSize: 12 }} />
                <Tooltip 
                  contentStyle={{ borderRadius: '8px', border: '1px solid #dadce0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1)' }}
                  itemStyle={{ color: '#d93025', fontWeight: 500 }}
                />
                <Area type="monotone" dataKey="outOfStock" name="缺货触发次数" stroke="#ea4335" strokeWidth={2} fillOpacity={1} fill="url(#colorOos)" />
              </AreaChart>
            </ResponsiveContainer>
            )}
          </div>
        </motion.div>

        {/* Recent Alerts */}
        {showAlerts && (
          <motion.div variants={itemVariants} className="bg-white p-6 rounded-2xl border border-[#dadce0] flex flex-col">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-[16px] font-medium text-[#202124]">最新告警</h2>
              <div className="flex items-center gap-3">
                <span className="bg-[#fce8e6] text-[#d93025] text-xs font-medium px-2 py-0.5 rounded-full">
                  {alerts.length} 条新消息
                </span>
                <button
                  onClick={() => setShowAlerts(false)}
                  className="p-1.5 text-[#5f6368] hover:bg-[#f1f3f4] rounded-full transition-colors"
                  title="关闭告警面板"
                >
                  <Icon name="close" size={20} />
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto pr-2 space-y-3">
              {loading ? (
                <div className="text-center text-[#5f6368] py-8">加载中...</div>
              ) : alerts.length === 0 ? (
                <div className="text-center text-[#5f6368] py-8">暂无告警</div>
              ) : (
                alerts.map((alert) => (
                <div 
                  key={alert.id} 
                  className={`p-3 rounded-lg border ${
                    alert.type === 'critical' 
                      ? 'bg-white border-[#fce8e6] shadow-[0_1px_2px_rgba(217,48,37,0.1)]' 
                      : 'bg-white border-[#fef7e0] shadow-[0_1px_2px_rgba(227,116,0,0.1)]'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`mt-0.5 shrink-0 ${alert.type === 'critical' ? 'text-[#d93025]' : 'text-[#e37400]'}`}>
                      <Icon name={alert.type === 'critical' ? 'inventory_2' : 'warning'} size={20} filled />
                    </div>
                    <div>
                      <p className={`text-[14px] font-medium text-[#202124]`}>
                        {alert.message}
                      </p>
                      <p className={`text-[12px] mt-0.5 ${alert.type === 'critical' ? 'text-[#d93025]' : 'text-[#e37400]'}`}>
                        {alert.time}
                      </p>
                    </div>
                  </div>
                </div>
              ))
              )}
            </div>
            <button 
              onClick={() => onNavigate('inventory')}
              className="w-full mt-4 py-2 border border-[#dadce0] rounded-full text-[14px] font-medium text-[#1a73e8] hover:bg-[#f8f9fa] hover:border-[#d2e3fc] transition-colors"
            >
              查看全部库存
            </button>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
