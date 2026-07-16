import { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, Legend, ResponsiveContainer, LineChart, Line } from 'recharts';
import { motion } from 'motion/react';
import { authenticatedFetch } from '../utils/auth';
import { Icon } from '../components/Icon';
import { cn } from '../utils/cn';

const REPORT_EXPORT_HISTORY_KEY = 'report_export_history';
const MAX_REPORT_HISTORY_ITEMS = 10;
const CATEGORY_FALLBACK_COLORS = [
  '#1a73e8',
  '#8ab4f8',
  '#fbbc04',
  '#34a853',
  '#ea4335',
  '#9334e6',
  '#00acc1',
  '#f29900',
];

type CategoryBreakdownCategory = {
  key: string;
  name: string;
  color?: string;
};

type CategoryBreakdownRow = {
  name: string;
  date?: string;
  values: Record<string, number>;
};

type CategoryBreakdownData = {
  categories: CategoryBreakdownCategory[];
  rows: CategoryBreakdownRow[];
};

type TrendAnalysisRow = {
  name: string;
  incidents?: number;
};

type StoredReport = {
  id: number;
  name: string;
  date: string;
  type: 'Excel';
  size: string;
  fileName: string;
  categoryData: CategoryBreakdownData;
  trendData: TrendAnalysisRow[];
};

type CategoryChartRow = {
  name: string;
  date?: string;
  values: Record<string, number>;
} & Record<string, string | number | Record<string, number> | undefined>;

function isCategoryBreakdownData(value: unknown): value is CategoryBreakdownData {
  if (!value || typeof value !== 'object') {
    return false;
  }

  const data = value as Partial<CategoryBreakdownData>;
  return Boolean(
    Array.isArray(data.categories) &&
      data.categories.every(
        (category) =>
          category &&
          typeof category.key === 'string' &&
          typeof category.name === 'string' &&
          (category.color === undefined || typeof category.color === 'string')
      ) &&
      Array.isArray(data.rows) &&
      data.rows.every(
        (row) =>
          row &&
          typeof row.name === 'string' &&
          (row.date === undefined || typeof row.date === 'string') &&
          row.values &&
          typeof row.values === 'object' &&
          !Array.isArray(row.values)
      )
  );
}

function getCategoryColor(category: CategoryBreakdownCategory, index: number) {
  return category.color || CATEGORY_FALLBACK_COLORS[index % CATEGORY_FALLBACK_COLORS.length];
}

function getCategoryDataKey(index: number) {
  return `category_${index}`;
}

function toCategoryChartRows(data: CategoryBreakdownData): CategoryChartRow[] {
  return data.rows.map((row) => {
    const chartRow: CategoryChartRow = {
      name: row.name,
      date: row.date,
      values: row.values,
    };

    data.categories.forEach((category, index) => {
      chartRow[getCategoryDataKey(index)] = Number(row.values[category.key] ?? 0);
    });

    return chartRow;
  });
}

function getTimeRangeLabel(timeRange: string) {
  if (timeRange === '7days') {
    return '最近7天';
  }

  if (timeRange === '30days') {
    return '最近30天';
  }

  return '本月';
}

function formatFileSize(bytes: number) {
  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return `${kilobytes.toFixed(1)} KB`;
  }

  return `${(kilobytes / 1024).toFixed(2)} MB`;
}

function loadStoredReports(): StoredReport[] {
  try {
    const rawValue = localStorage.getItem(REPORT_EXPORT_HISTORY_KEY);
    if (!rawValue) {
      return [];
    }

    const parsedValue = JSON.parse(rawValue);
    if (!Array.isArray(parsedValue)) {
      return [];
    }

    return parsedValue.filter((item): item is StoredReport => {
      return Boolean(
        item &&
          typeof item.id === 'number' &&
          typeof item.name === 'string' &&
          typeof item.date === 'string' &&
          item.type === 'Excel' &&
          typeof item.size === 'string' &&
          typeof item.fileName === 'string' &&
          isCategoryBreakdownData(item.categoryData) &&
          Array.isArray(item.trendData)
      );
    });
  } catch {
    return [];
  }
}

function persistStoredReports(reports: StoredReport[]) {
  localStorage.setItem(
    REPORT_EXPORT_HISTORY_KEY,
    JSON.stringify(reports.slice(0, MAX_REPORT_HISTORY_ITEMS))
  );
}

async function buildWorkbook(
  loadSpreadsheetModule: () => Promise<typeof import('xlsx')>,
  report: Pick<StoredReport, 'categoryData' | 'trendData'>
) {
  const XLSX = await loadSpreadsheetModule();
  const workbook = XLSX.utils.book_new();

  const categorySheetData = report.categoryData.rows.map((item) => {
    const sheetRow: Record<string, string | number> = {
      日期: item.date || item.name,
    };

    report.categoryData.categories.forEach((category) => {
      sheetRow[category.name] = item.values[category.key] ?? 0;
    });

    return sheetRow;
  });
  const categorySheet = XLSX.utils.json_to_sheet(categorySheetData);
  XLSX.utils.book_append_sheet(workbook, categorySheet, '各品类缺货统计');

  const trendSheetData = report.trendData.map((item) => ({
    日期: item.name,
    库存异常次数: item.incidents ?? 0,
  }));
  const trendSheet = XLSX.utils.json_to_sheet(trendSheetData);
  XLSX.utils.book_append_sheet(workbook, trendSheet, '缺货趋势');

  const workbookArray = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' });
  return { XLSX, workbook, workbookSize: workbookArray.byteLength };
}

export function Reports() {
  const [timeRange, setTimeRange] = useState('thisMonth');
  const [categoryData, setCategoryData] = useState<CategoryBreakdownData>({
    categories: [],
    rows: [],
  });
  const [trendData, setTrendData] = useState<TrendAnalysisRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [reportsList, setReportsList] = useState<StoredReport[]>(() => loadStoredReports()); /*
    {
      id: 1,
      name: '每周补货优化建议报表',
      date: '2023年10月14日',
      type: 'PDF',
      size: '2.4 MB',
      data: null,
      fileName: ''
    },
    {
      id: 2,
      name: '每周补货优化建议报表',
      date: '2023年10月13日',
      type: 'PDF',
      size: '2.4 MB',
      data: null,
      fileName: ''
    },
    {
      id: 3,
      name: '每周补货优化建议报表',
      date: '2023年10月12日',
      type: 'PDF',
      size: '2.4 MB',
      data: null,
      fileName: ''
    }
  ]); */

  // Load data from API
  useEffect(() => {
    void loadRealReportData();
  }, [timeRange]);

  const loadSpreadsheetModule = () => import('xlsx');

  const loadRealReportData = async () => {
    try {
      setLoading(true);
      const days =
        timeRange === '7days' ? 7 : timeRange === '30days' ? 30 : new Date().getDate();

      const categoryResponse = await authenticatedFetch(
        `/api/v1/reports/category-breakdown?days=${days}`
      );
      if (categoryResponse.ok) {
        const categoryPayload = await categoryResponse.json();
        setCategoryData(
          isCategoryBreakdownData(categoryPayload) ? categoryPayload : { categories: [], rows: [] }
        );
      } else {
        setCategoryData({ categories: [], rows: [] });
      }

      const trendResponse = await authenticatedFetch(`/api/v1/reports/trend-analysis?days=${days}`);
      if (trendResponse.ok) {
        const trendPayload = (await trendResponse.json()) as TrendAnalysisRow[];
        setTrendData(trendPayload);
      } else {
        setTrendData([]);
      }
    } catch (error) {
      console.error('Error loading report data:', error);
      setCategoryData({ categories: [], rows: [] });
      setTrendData([]);
    } finally {
      setLoading(false);
    }
  };

  const handleExportRealReport = async () => {
    const timeRangeLabel = getTimeRangeLabel(timeRange);
    const exportedAt = new Date();
    const fileName = `缺货统计报表_${timeRangeLabel}_${exportedAt.getTime()}.xlsx`;
    const { XLSX, workbook, workbookSize } = await buildWorkbook(loadSpreadsheetModule, {
      categoryData,
      trendData,
    });

    XLSX.writeFile(workbook, fileName);

    const nextReport: StoredReport = {
      id: exportedAt.getTime(),
      name: `缺货统计报表（${timeRangeLabel}）`,
      date: exportedAt.toLocaleString('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }),
      type: 'Excel',
      size: formatFileSize(workbookSize),
      fileName,
      categoryData,
      trendData,
    };

    setReportsList((previousReports) => {
      const updatedReports = [nextReport, ...previousReports].slice(0, MAX_REPORT_HISTORY_ITEMS);
      persistStoredReports(updatedReports);
      return updatedReports;
    });
  };

  const handleDownloadStoredReport = async (report: StoredReport) => {
    const { XLSX, workbook } = await buildWorkbook(loadSpreadsheetModule, report);
    XLSX.writeFile(workbook, report.fileName);
  };

  const categoryChartData = toCategoryChartRows(categoryData);

  return (
    <motion.div 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="space-y-6"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800 tracking-tight">统计与分析报表</h1>
          <p className="text-slate-500 mt-1 text-sm">分析缺货趋势，优化补货周期。</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center bg-white border border-[#dadce0] rounded-full px-4 py-2 hover:bg-slate-50 transition-colors">
            <Icon name="calendar_today" size={18} className="text-slate-500 mr-2" />
            <select 
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
              className="bg-transparent text-sm font-medium text-slate-700 outline-none border-none cursor-pointer"
            >
              <option value="7days">最近 7 天</option>
              <option value="30days">最近 30 天</option>
              <option value="thisMonth">本月</option>
            </select>
          </div>
          <motion.button 
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => {
              void handleExportRealReport();
            }}
            className="px-5 py-2 bg-[#0b57d0] text-white rounded-full text-sm font-medium hover:bg-[#0842a0] flex items-center gap-2 transition-colors"
          >
            <Icon name="download" size={18} />
            导出报表
          </motion.button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Weekly Breakdown */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.1, duration: 0.4 }}
          className="bg-white p-6 rounded-3xl border border-[#dadce0]"
        >
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-bold text-slate-800">各品类缺货统计</h2>
            <Icon name="bar_chart" className="text-slate-400" />
          </div>
          {loading ? (
            <div className="h-80 flex flex-col items-center justify-center text-slate-400 gap-2">
              <Icon name="sync" className="animate-spin" />
              <span>加载中...</span>
            </div>
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={categoryChartData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <RechartsTooltip cursor={{fill: '#f8fafc'}} contentStyle={{ borderRadius: '12px', border: '1px solid #dadce0', boxShadow: 'none' }} />
                  <Legend
                    iconType="circle"
                    wrapperStyle={{ paddingTop: '20px', lineHeight: '24px' }}
                  />
                  {categoryData.categories.map((category, index) => (
                    <Bar
                      key={category.key}
                      dataKey={getCategoryDataKey(index)}
                      name={category.name}
                      stackId="a"
                      fill={getCategoryColor(category, index)}
                      radius={
                        categoryData.categories.length === 1
                          ? [4, 4, 4, 4]
                          : index === 0
                            ? [0, 0, 4, 4]
                            : index === categoryData.categories.length - 1
                              ? [4, 4, 0, 0]
                              : [0, 0, 0, 0]
                      }
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </motion.div>

        {/* Monthly Trend */}
        <motion.div 
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2, duration: 0.4 }}
          className="bg-white p-6 rounded-3xl border border-[#dadce0]"
        >
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-bold text-slate-800">缺货趋势</h2>
            <Icon name="trending_up" className="text-slate-400" />
          </div>
          {loading ? (
            <div className="h-80 flex flex-col items-center justify-center text-slate-400 gap-2">
              <Icon name="sync" className="animate-spin" />
              <span>加载中...</span>
            </div>
          ) : (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                  <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} dy={10} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                  <RechartsTooltip contentStyle={{ borderRadius: '12px', border: '1px solid #dadce0', boxShadow: 'none' }} />
                  <Line type="monotone" dataKey="incidents" name="库存异常次数" stroke="#1a73e8" strokeWidth={3} dot={{ r: 4, fill: '#1a73e8', strokeWidth: 2, stroke: '#fff' }} activeDot={{ r: 6 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </motion.div>
      </div>

      {/* Generated Reports List */}
      <motion.div 
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3, duration: 0.4 }}
        className="bg-white rounded-3xl border border-[#dadce0] overflow-hidden"
      >
        <div className="p-6 border-b border-[#dadce0] flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-800">最近生成的报表</h2>
        </div>
        <div className="divide-y divide-[#dadce0]">
          {reportsList.length === 0 ? (
            <div className="p-8 text-center text-sm text-slate-500">无</div>
          ) : (
            reportsList.map((report, index) => (
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.1 * index }}
              key={report.id} 
              className="p-4 flex items-center justify-between hover:bg-slate-50 transition-colors"
            >
              <div className="flex items-center gap-4">
                <div className={cn(
                  "w-12 h-12 rounded-2xl flex items-center justify-center",
                  report.type === 'Excel' ? 'bg-[#e6f4ea] text-[#137333]' : 'bg-[#e8f0fe] text-[#1a73e8]'
                )}>
                  <Icon name={report.type === 'Excel' ? 'table_view' : 'description'} size={24} />
                </div>
                <div>
                  <p className="font-medium text-slate-800">{report.name}</p>
                  <p className="text-sm text-slate-500 mt-0.5">生成于 {report.date} • {report.type} • {report.size}</p>
                </div>
                </div>
                <button 
                  onClick={() => {
                    void handleDownloadStoredReport(report);
                  }}
                  className="text-[#0b57d0] hover:text-[#0842a0] text-sm font-medium px-4 py-2 rounded-full hover:bg-[#e8f0fe] transition-colors flex items-center gap-2"
                >
                  <Icon name="download" size={18} />
                  下载
                </button>
              </motion.div>
            ))
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
