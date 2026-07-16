import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';

import { Icon } from '../components/Icon';
import { LabelMappingManager } from '../components/LabelMappingManager';
import { authenticatedFetch, getUser } from '../utils/auth';
import { cn } from '../utils/cn';

type InventoryItem = {
  id: string;
  name: string;
  category: string;
  aisle: string;
  current_stock: number;
  threshold: number;
  status: 'normal' | 'low' | 'out';
};

type InventoryFormState = {
  id: string;
  name: string;
  category: string;
  aisle: string;
  current_stock: string;
  threshold: string;
};

type Feedback = {
  type: 'success' | 'error';
  message: string;
} | null;

type SortField = 'id' | 'name' | 'category' | 'current_stock' | 'threshold' | 'status';
type SortDirection = 'asc' | 'desc';

type SortState = {
  field: SortField;
  direction: SortDirection;
};

const createEmptyForm = (defaultThreshold: number): InventoryFormState => ({
  id: '',
  name: '',
  category: '',
  aisle: '',
  current_stock: '0',
  threshold: String(defaultThreshold),
});

function deriveStatus(currentStock: number, threshold: number) {
  if (currentStock <= 0) {
    return 'out';
  }
  if (currentStock < threshold) {
    return 'low';
  }
  return 'normal';
}

function compareInventoryItems(
  left: InventoryItem,
  right: InventoryItem,
  field: SortField,
  direction: SortDirection
) {
  const multiplier = direction === 'asc' ? 1 : -1;
  const leftValue = left[field];
  const rightValue = right[field];

  if (typeof leftValue === 'number' && typeof rightValue === 'number') {
    return (leftValue - rightValue) * multiplier;
  }

  return String(leftValue).localeCompare(String(rightValue), 'zh-CN', {
    numeric: true,
    sensitivity: 'base',
  }) * multiplier;
}

const INVENTORY_PAGE_SIZE = 10;

export function InventoryManagement() {
  const user = getUser();
  const isAdmin = Boolean(user?.is_admin);

  const [inventoryData, setInventoryData] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [stockMin, setStockMin] = useState('');
  const [stockMax, setStockMax] = useState('');
  const [thresholdMin, setThresholdMin] = useState('');
  const [thresholdMax, setThresholdMax] = useState('');
  const [defaultThreshold, setDefaultThreshold] = useState(10);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create');
  const [form, setForm] = useState<InventoryFormState>(createEmptyForm(10));
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<Feedback>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [sortState, setSortState] = useState<SortState>({
    field: 'id',
    direction: 'asc',
  });

  useEffect(() => {
    void loadInventory({
      showLoading: inventoryData.length === 0,
    });
    if (isAdmin) {
      void loadDefaultThreshold();
    }
  }, [isAdmin, sortState.field, sortState.direction]);

  const loadInventory = async (options: { showLoading?: boolean } = {}) => {
    try {
      if (options.showLoading ?? inventoryData.length === 0) {
        setLoading(true);
      }
      const params = new URLSearchParams({
        limit: '500',
        order_by: sortState.field,
        order_dir: sortState.direction,
      });
      const response = await authenticatedFetch(`/api/v1/inventory/?${params.toString()}`);
      if (!response.ok) {
        throw new Error('加载库存数据失败');
      }

      const data = (await response.json()) as InventoryItem[];
      setInventoryData(data);
    } catch (error) {
      console.error('Error loading inventory:', error);
      setFeedback({
        type: 'error',
        message: '库存数据加载失败，请稍后重试。',
      });
    } finally {
      setLoading(false);
    }
  };

  const loadDefaultThreshold = async () => {
    try {
      const response = await authenticatedFetch('/api/v1/settings');
      if (!response.ok) {
        return;
      }

      const data = await response.json();
      setDefaultThreshold(data.default_item_threshold);
    } catch (error) {
      console.error('Error loading settings:', error);
    }
  };

  const categories = Array.from(
    new Set(inventoryData.map((item) => item.category).filter(Boolean))
  );

  const filteredData = useMemo(() => {
    const filteredItems = inventoryData.filter((item) => {
      const matchSearch =
        item.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.id.toLowerCase().includes(searchTerm.toLowerCase());
      const matchCategory = categoryFilter ? item.category === categoryFilter : true;
      const matchStatus = statusFilter ? item.status === statusFilter : true;
      const matchStockMin = stockMin ? item.current_stock >= Number(stockMin) : true;
      const matchStockMax = stockMax ? item.current_stock <= Number(stockMax) : true;
      const matchThresholdMin = thresholdMin
        ? item.threshold >= Number(thresholdMin)
        : true;
      const matchThresholdMax = thresholdMax
        ? item.threshold <= Number(thresholdMax)
        : true;

      return (
        matchSearch &&
        matchCategory &&
        matchStatus &&
        matchStockMin &&
        matchStockMax &&
        matchThresholdMin &&
        matchThresholdMax
      );
    });
    return [...filteredItems].sort((left, right) =>
      compareInventoryItems(left, right, sortState.field, sortState.direction)
    );
  }, [
    inventoryData,
    searchTerm,
    categoryFilter,
    statusFilter,
    stockMin,
    stockMax,
    thresholdMin,
    thresholdMax,
    sortState.field,
    sortState.direction,
  ]);

  useEffect(() => {
    setCurrentPage(1);
  }, [
    searchTerm,
    categoryFilter,
    statusFilter,
    stockMin,
    stockMax,
    thresholdMin,
    thresholdMax,
  ]);

  const totalPages = Math.max(1, Math.ceil(filteredData.length / INVENTORY_PAGE_SIZE));
  const effectiveCurrentPage = Math.min(currentPage, totalPages);

  useEffect(() => {
    if (currentPage !== effectiveCurrentPage) {
      setCurrentPage(effectiveCurrentPage);
    }
  }, [currentPage, effectiveCurrentPage]);

  const paginatedData = useMemo(() => {
    const startIndex = (effectiveCurrentPage - 1) * INVENTORY_PAGE_SIZE;
    return filteredData.slice(startIndex, startIndex + INVENTORY_PAGE_SIZE);
  }, [effectiveCurrentPage, filteredData]);

  const pageStart =
    filteredData.length === 0 ? 0 : (effectiveCurrentPage - 1) * INVENTORY_PAGE_SIZE + 1;
  const pageEnd =
    filteredData.length === 0
      ? 0
      : Math.min(effectiveCurrentPage * INVENTORY_PAGE_SIZE, filteredData.length);
  const visiblePage = filteredData.length === 0 ? 0 : effectiveCurrentPage;
  const visibleTotalPages = filteredData.length === 0 ? 0 : totalPages;

  const formStatusPreview = useMemo(() => {
    const currentStock = Number(form.current_stock);
    const threshold = Number(form.threshold);
    if (Number.isNaN(currentStock) || Number.isNaN(threshold)) {
      return 'normal';
    }
    return deriveStatus(currentStock, threshold);
  }, [form.current_stock, form.threshold]);

  const clearFilters = () => {
    setSearchTerm('');
    setCategoryFilter('');
    setStatusFilter('');
    setStockMin('');
    setStockMax('');
    setThresholdMin('');
    setThresholdMax('');
  };

  const handleSort = (field: SortField) => {
    setSortState((current) => ({
      field,
      direction: current.field === field && current.direction === 'asc' ? 'desc' : 'asc',
    }));
    setCurrentPage(1);
  };

  const renderSortableHeader = (
    field: SortField,
    label: string,
    align: 'left' | 'right' = 'left'
  ) => {
    const isActive = sortState.field === field;
    const iconName = isActive
      ? sortState.direction === 'asc'
        ? 'arrow_upward'
        : 'arrow_downward'
      : 'unfold_more';

    return (
      <button
        type="button"
        onClick={() => handleSort(field)}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full text-sm font-medium transition-colors hover:text-[#0b57d0]',
          align === 'right' ? 'ml-auto justify-end' : 'justify-start',
          isActive ? 'text-[#0b57d0]' : 'text-slate-600'
        )}
      >
        <span>{label}</span>
        <Icon
          name={iconName}
          size={16}
          className={isActive ? 'text-[#0b57d0]' : 'text-slate-400'}
        />
      </button>
    );
  };

  const closeModal = () => {
    setIsModalOpen(false);
    setForm(createEmptyForm(defaultThreshold));
  };

  const openCreateModal = () => {
    setFormMode('create');
    setForm(createEmptyForm(defaultThreshold));
    setFeedback(null);
    setIsModalOpen(true);
  };

  const openEditModal = (item: InventoryItem) => {
    setFormMode('edit');
    setForm({
      id: item.id,
      name: item.name,
      category: item.category,
      aisle: item.aisle,
      current_stock: String(item.current_stock),
      threshold: String(item.threshold),
    });
    setFeedback(null);
    setIsModalOpen(true);
  };

  const setFormField = (field: keyof InventoryFormState, value: string) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const handleExportCSV = () => {
    const headers = ['商品编号', '名称', '分类', '当前库存', '预警阈值', '状态'];
    const csvContent = [
      headers.join(','),
      ...filteredData.map(
        (item) =>
          `${item.id},${item.name},${item.category},${item.current_stock},${item.threshold},${item.status}`
      ),
    ].join('\n');

    const blob = new Blob(['\uFEFF' + csvContent], {
      type: 'text/csv;charset=utf-8;',
    });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', 'inventory_export.csv');
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleSubmitItem = async () => {
    if (!form.id.trim() || !form.name.trim()) {
      setFeedback({
        type: 'error',
        message: '请至少填写商品编号和名称。',
      });
      return;
    }

    if (!form.category.trim() || !form.aisle.trim()) {
      setFeedback({
        type: 'error',
        message: '请填写商品分类和货道位置。',
      });
      return;
    }

    const currentStock = Number(form.current_stock);
    const threshold = Number(form.threshold);

    if (Number.isNaN(currentStock) || currentStock < 0) {
      setFeedback({
        type: 'error',
        message: '当前库存必须是大于等于 0 的数字。',
      });
      return;
    }

    if (Number.isNaN(threshold) || threshold < 0) {
      setFeedback({
        type: 'error',
        message: '预警阈值必须是大于等于 0 的数字。',
      });
      return;
    }

    try {
      setSaving(true);
      const payload = {
        ...(formMode === 'create' ? { id: form.id.trim() } : {}),
        name: form.name.trim(),
        category: form.category.trim(),
        aisle: form.aisle.trim(),
        current_stock: currentStock,
        threshold,
      };

      const response = await authenticatedFetch(
        formMode === 'create'
          ? '/api/v1/inventory/'
          : `/api/v1/inventory/${form.id}`,
        {
          method: formMode === 'create' ? 'POST' : 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '保存商品失败');
      }

      await loadInventory();
      closeModal();
      setFeedback({
        type: 'success',
        message:
          formMode === 'create'
            ? '商品已创建，并同步写入库存历史。'
            : '商品已更新，库存状态与告警已同步联动。',
      });
    } catch (error: any) {
      console.error('Error saving item:', error);
      setFeedback({
        type: 'error',
        message: error.message || '保存商品失败，请稍后重试。',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (itemId: string) => {
    if (!window.confirm('确定要删除这个商品吗？')) {
      return;
    }

    try {
      const response = await authenticatedFetch(`/api/v1/inventory/${itemId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || '删除商品失败');
      }

      setInventoryData((current) => current.filter((item) => item.id !== itemId));
      setFeedback({
        type: 'success',
        message: '商品已删除。',
      });
    } catch (error: any) {
      console.error('Error deleting item:', error);
      setFeedback({
        type: 'error',
        message: error.message || '删除商品失败，请稍后重试。',
      });
    }
  };

  const getStatusBadge = (status: InventoryItem['status']) => {
    switch (status) {
      case 'normal':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700">
            <Icon name="check_circle" size={14} filled /> 正常
          </span>
        );
      case 'low':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-700">
            <Icon name="warning" size={14} filled /> 低库存
          </span>
        );
      case 'out':
        return (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
            <Icon name="error" size={14} filled /> 缺货
          </span>
        );
      default:
        return null;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="space-y-6"
    >
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-800">库存管理</h1>
          <p className="mt-1 text-sm text-slate-500">
            管理商品信息、阈值与库存，并将手动库存调整真实写入库存历史。
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setShowFilters((value) => !value)}
            className={cn(
              'flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-colors',
              showFilters
                ? 'border-slate-300 bg-slate-100 text-slate-800'
                : 'border-[#dadce0] bg-white text-slate-600 hover:bg-slate-50'
            )}
          >
            <Icon name="filter_list" size={18} />
            筛选
          </motion.button>
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handleExportCSV}
            className="flex items-center gap-2 rounded-full bg-[#0b57d0] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#0842a0]"
          >
            <Icon name="download" size={18} />
            导出 CSV
          </motion.button>
          {isAdmin && (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={openCreateModal}
              className="flex items-center gap-2 rounded-full bg-[#137333] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#0f5c2a]"
            >
              <Icon name="add" size={18} />
              新增商品
            </motion.button>
          )}
        </div>
      </div>

      {feedback && (
        <div
          className={cn(
            'rounded-2xl border px-4 py-3 text-sm font-medium',
            feedback.type === 'success'
              ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
              : 'border-red-200 bg-red-50 text-red-700'
          )}
        >
          {feedback.message}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-[#dadce0] bg-white">
        <div className="flex flex-col gap-4 border-b border-[#dadce0] p-4">
          <div className="flex items-center gap-4">
            <div className="relative max-w-md flex-1">
              <Icon
                name="search"
                size={20}
                className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                type="text"
                placeholder="按商品名称或编号搜索..."
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                className="w-full rounded-full border border-transparent bg-slate-50 py-2.5 pl-11 pr-4 text-sm outline-none transition-all placeholder-slate-400 focus:border-[#dadce0] focus:bg-white focus:ring-1 focus:ring-[#0b57d0]"
              />
            </div>
            {showFilters && (
              <button
                onClick={clearFilters}
                className="flex items-center gap-1 px-2 text-sm font-medium text-[#0b57d0] hover:text-[#0842a0]"
              >
                <Icon name="close" size={16} />
                清空
              </button>
            )}
          </div>

          <AnimatePresence>
            {showFilters && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="grid grid-cols-1 gap-4 border-t border-[#dadce0] pt-4 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">分类</label>
                    <select
                      value={categoryFilter}
                      onChange={(event) => setCategoryFilter(event.target.value)}
                      className="w-full rounded-xl border border-transparent bg-slate-50 px-4 py-2 text-sm outline-none transition-all focus:border-[#0b57d0] focus:bg-white"
                    >
                      <option value="">全部</option>
                      {categories.map((category) => (
                        <option key={category} value={category}>
                          {category}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">状态</label>
                    <select
                      value={statusFilter}
                      onChange={(event) => setStatusFilter(event.target.value)}
                      className="w-full rounded-xl border border-transparent bg-slate-50 px-4 py-2 text-sm outline-none transition-all focus:border-[#0b57d0] focus:bg-white"
                    >
                      <option value="">全部</option>
                      <option value="normal">正常</option>
                      <option value="low">低库存</option>
                      <option value="out">缺货</option>
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">库存范围</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        placeholder="最小"
                        value={stockMin}
                        onChange={(event) => setStockMin(event.target.value)}
                        className="w-full rounded-xl border border-transparent bg-slate-50 px-3 py-2 text-sm outline-none transition-all focus:border-[#0b57d0] focus:bg-white"
                      />
                      <span className="text-slate-400">-</span>
                      <input
                        type="number"
                        placeholder="最大"
                        value={stockMax}
                        onChange={(event) => setStockMax(event.target.value)}
                        className="w-full rounded-xl border border-transparent bg-slate-50 px-3 py-2 text-sm outline-none transition-all focus:border-[#0b57d0] focus:bg-white"
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">阈值范围</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        placeholder="最小"
                        value={thresholdMin}
                        onChange={(event) => setThresholdMin(event.target.value)}
                        className="w-full rounded-xl border border-transparent bg-slate-50 px-3 py-2 text-sm outline-none transition-all focus:border-[#0b57d0] focus:bg-white"
                      />
                      <span className="text-slate-400">-</span>
                      <input
                        type="number"
                        placeholder="最大"
                        value={thresholdMax}
                        onChange={(event) => setThresholdMax(event.target.value)}
                        className="w-full rounded-xl border border-transparent bg-slate-50 px-3 py-2 text-sm outline-none transition-all focus:border-[#0b57d0] focus:bg-white"
                      />
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="overflow-x-auto">
          {loading ? (
            <div className="flex items-center justify-center gap-2 p-12 text-slate-500">
              <Icon name="sync" size={20} className="animate-spin" />
              <span>正在加载库存数据...</span>
            </div>
          ) : (
            <table className="w-full border-collapse text-left text-sm text-slate-700">
              <thead className="border-b border-[#dadce0] bg-[#f8f9fa]">
                <tr>
                  <th className="whitespace-nowrap px-6 py-4 font-medium text-slate-600">
                    {renderSortableHeader('id', '商品编号')}
                  </th>
                  <th className="whitespace-nowrap px-6 py-4 font-medium text-slate-600">
                    {renderSortableHeader('name', '名称')}
                  </th>
                  <th className="whitespace-nowrap px-6 py-4 font-medium text-slate-600">
                    {renderSortableHeader('category', '分类')}
                  </th>
                  <th className="whitespace-nowrap px-6 py-4 text-right font-medium text-slate-600">
                    {renderSortableHeader('current_stock', '当前库存', 'right')}
                  </th>
                  <th className="whitespace-nowrap px-6 py-4 text-right font-medium text-slate-600">
                    {renderSortableHeader('threshold', '预警阈值', 'right')}
                  </th>
                  <th className="whitespace-nowrap px-6 py-4 font-medium text-slate-600">
                    {renderSortableHeader('status', '状态')}
                  </th>
                  {isAdmin && (
                    <th className="whitespace-nowrap px-6 py-4 text-right font-medium text-slate-600">操作</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#dadce0]">
                {paginatedData.length > 0 ? (
                  paginatedData.map((item, index) => (
                    <motion.tr
                      key={item.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.02, duration: 0.3 }}
                      className="group transition-colors hover:bg-slate-50"
                    >
                      <td className="px-6 py-4 font-mono text-xs text-slate-500">{item.id}</td>
                      <td className="px-6 py-4 font-medium text-slate-800">{item.name}</td>
                      <td className="px-6 py-4">
                        <span className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                          {item.category}
                        </span>
                      </td>
                      <td
                        className={cn(
                          'px-6 py-4 text-right font-bold',
                          item.status === 'out'
                            ? 'text-red-600'
                            : item.status === 'low'
                              ? 'text-amber-600'
                              : 'text-slate-800'
                        )}
                      >
                        {item.current_stock}
                      </td>
                      <td className="px-6 py-4 text-right text-slate-500">{item.threshold}</td>
                      <td className="px-6 py-4">{getStatusBadge(item.status)}</td>
                      {isAdmin && (
                        <td className="px-6 py-4 text-right">
                          <div className="flex justify-end gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                            <button
                              onClick={() => openEditModal(item)}
                              title="编辑商品"
                              className="rounded-full p-2 text-slate-400 transition-colors hover:bg-[#e8f0fe] hover:text-[#1a73e8]"
                            >
                              <Icon name="edit" size={20} />
                            </button>
                            <button
                              onClick={() => handleDelete(item.id)}
                              title="删除商品"
                              className="rounded-full p-2 text-slate-400 transition-colors hover:bg-red-50 hover:text-red-600"
                            >
                              <Icon name="delete" size={20} />
                            </button>
                          </div>
                        </td>
                      )}
                    </motion.tr>
                  ))
                ) : (
                  <tr>
                    <td
                      colSpan={isAdmin ? 7 : 6}
                      className="px-6 py-12 text-center text-slate-500"
                    >
                      没有找到匹配的商品记录。
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-[#dadce0] p-4 text-sm text-slate-500">
          <div className="flex flex-col gap-1">
            <span>显示 {pageStart}-{pageEnd} 条，共 {filteredData.length} 条筛选结果</span>
            <span>
              第 {visiblePage} / {visibleTotalPages} 页，每页 {INVENTORY_PAGE_SIZE} 条，共 {inventoryData.length} 条库存记录
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-slate-100 px-3 py-2 text-slate-600">
              {visiblePage}/{visibleTotalPages}
            </span>
            <button
              onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
              className="rounded-full border border-[#dadce0] px-4 py-2 transition-colors hover:bg-slate-50 disabled:opacity-50"
              disabled={effectiveCurrentPage <= 1 || filteredData.length === 0}
            >
              上一页
            </button>
            <button
              onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
              className="rounded-full border border-[#dadce0] px-4 py-2 transition-colors hover:bg-slate-50 disabled:opacity-50"
              disabled={effectiveCurrentPage >= totalPages || filteredData.length === 0}
            >
              下一页
            </button>
          </div>
        </div>

      </div>

      {isAdmin && (
        <LabelMappingManager
          items={inventoryData.map((item) => ({
            id: item.id,
            name: item.name,
          }))}
        />
      )}

      <AnimatePresence>
        {isModalOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4 backdrop-blur-sm"
          >
            <motion.div
              initial={{ opacity: 0, y: 24, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 12, scale: 0.98 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-2xl rounded-3xl border border-[#dadce0] bg-white shadow-xl"
            >
              <div className="flex items-center justify-between border-b border-[#dadce0] px-6 py-5">
                <div>
                  <h2 className="text-lg font-bold text-slate-800">
                    {formMode === 'create' ? '新增商品' : '编辑商品'}
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    保存后会自动联动库存状态、库存历史和相关告警。
                  </p>
                </div>
                <button
                  onClick={closeModal}
                  className="rounded-full p-2 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
                  title="关闭"
                >
                  <Icon name="close" size={20} />
                </button>
              </div>

              <div className="space-y-6 px-6 py-6">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">商品编号</label>
                    <input
                      type="text"
                      value={form.id}
                      onChange={(event) => setFormField('id', event.target.value)}
                      disabled={formMode === 'edit'}
                      className={cn(
                        'w-full rounded-xl border px-4 py-3 text-sm outline-none transition-all',
                        formMode === 'edit'
                          ? 'cursor-not-allowed border-[#dadce0] bg-slate-100 text-slate-500'
                          : 'border-[#dadce0] bg-white focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]'
                      )}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">商品名称</label>
                    <input
                      type="text"
                      value={form.name}
                      onChange={(event) => setFormField('name', event.target.value)}
                      className="w-full rounded-xl border border-[#dadce0] bg-white px-4 py-3 text-sm outline-none transition-all focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">分类</label>
                    <input
                      type="text"
                      value={form.category}
                      onChange={(event) => setFormField('category', event.target.value)}
                      className="w-full rounded-xl border border-[#dadce0] bg-white px-4 py-3 text-sm outline-none transition-all focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">货道</label>
                    <input
                      type="text"
                      value={form.aisle}
                      onChange={(event) => setFormField('aisle', event.target.value)}
                      className="w-full rounded-xl border border-[#dadce0] bg-white px-4 py-3 text-sm outline-none transition-all focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">当前库存</label>
                    <input
                      type="number"
                      min="0"
                      value={form.current_stock}
                      onChange={(event) => setFormField('current_stock', event.target.value)}
                      className="w-full rounded-xl border border-[#dadce0] bg-white px-4 py-3 text-sm outline-none transition-all focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-medium text-slate-600">预警阈值</label>
                    <input
                      type="number"
                      min="0"
                      value={form.threshold}
                      onChange={(event) => setFormField('threshold', event.target.value)}
                      className="w-full rounded-xl border border-[#dadce0] bg-white px-4 py-3 text-sm outline-none transition-all focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                    />
                  </div>
                </div>

                <div className="rounded-2xl border border-[#dadce0] bg-[#f8f9fa] px-4 py-3 text-sm text-slate-600">
                  <div className="flex items-center justify-between gap-4">
                    <span>状态将由库存与阈值自动计算</span>
                    <div>{getStatusBadge(formStatusPreview)}</div>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 border-t border-[#dadce0] px-6 py-5">
                <button
                  onClick={closeModal}
                  className="rounded-full border border-[#dadce0] px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
                >
                  取消
                </button>
                <button
                  onClick={handleSubmitItem}
                  disabled={saving}
                  className="rounded-full bg-[#1a73e8] px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-[#1557b0] disabled:opacity-60"
                >
                  {saving ? '保存中...' : formMode === 'create' ? '创建商品' : '保存修改'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
