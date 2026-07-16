import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { authenticatedFetch } from '../utils/auth';
import { Icon } from './Icon';

type ItemOption = {
  id: string;
  name: string;
};

type LabelMapping = {
  id: number;
  detection_label: string;
  item_id: string;
  item_name: string;
};

type MappingFormState = {
  detection_label: string;
  item_id: string;
};

const emptyForm: MappingFormState = {
  detection_label: '',
  item_id: '',
};

const MAPPINGS_PAGE_SIZE = 10;

export const LabelMappingManager = ({ items }: { items: ItemOption[] }) => {
  const [mappings, setMappings] = useState<LabelMapping[]>([]);
  const [form, setForm] = useState<MappingFormState>(emptyForm);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const itemOptions = useMemo(
    () => items.map((item) => ({ id: item.id, label: `${item.name} (${item.id})` })),
    [items]
  );

  const loadMappings = async () => {
    try {
      setLoading(true);
      setError('');
      const response = await authenticatedFetch('/api/v1/label-mappings/');
      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail || '加载标签映射失败');
      }

      const result = await response.json();
      setMappings(result);
    } catch (loadError: any) {
      setError(loadError.message || '加载标签映射失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMappings();
  }, []);

  const totalPages = Math.max(1, Math.ceil(mappings.length / MAPPINGS_PAGE_SIZE));
  const effectiveCurrentPage = Math.min(currentPage, totalPages);

  useEffect(() => {
    if (currentPage !== effectiveCurrentPage) {
      setCurrentPage(effectiveCurrentPage);
    }
  }, [currentPage, effectiveCurrentPage]);

  const paginatedMappings = useMemo(() => {
    const startIndex = (effectiveCurrentPage - 1) * MAPPINGS_PAGE_SIZE;
    return mappings.slice(startIndex, startIndex + MAPPINGS_PAGE_SIZE);
  }, [effectiveCurrentPage, mappings]);

  const pageStart =
    mappings.length === 0 ? 0 : (effectiveCurrentPage - 1) * MAPPINGS_PAGE_SIZE + 1;
  const pageEnd =
    mappings.length === 0 ? 0 : Math.min(effectiveCurrentPage * MAPPINGS_PAGE_SIZE, mappings.length);
  const visiblePage = mappings.length === 0 ? 0 : effectiveCurrentPage;
  const visibleTotalPages = mappings.length === 0 ? 0 : totalPages;

  const resetForm = () => {
    setForm(emptyForm);
    setEditingId(null);
    setError('');
  };

  const handleSubmit = async () => {
    if (!form.detection_label.trim() || !form.item_id) {
      setError('请先填写检测标签并选择商品');
      return;
    }

    try {
      setSaving(true);
      setError('');

      const response = await authenticatedFetch(
        editingId === null
          ? '/api/v1/label-mappings/'
          : `/api/v1/label-mappings/${editingId}`,
        {
          method: editingId === null ? 'POST' : 'PATCH',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            detection_label: form.detection_label.trim(),
            item_id: form.item_id,
          }),
        }
      );

      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail || '保存标签映射失败');
      }

      await loadMappings();
      resetForm();
    } catch (submitError: any) {
      setError(submitError.message || '保存标签映射失败');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (mapping: LabelMapping) => {
    setEditingId(mapping.id);
    setForm({
      detection_label: mapping.detection_label,
      item_id: mapping.item_id,
    });
    setError('');
  };

  const handleDelete = async (mappingId: number) => {
    if (!window.confirm('确定删除这条标签映射吗？')) {
      return;
    }

    try {
      setSaving(true);
      setError('');

      const response = await authenticatedFetch(`/api/v1/label-mappings/${mappingId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.detail || '删除标签映射失败');
      }

      await loadMappings();
      if (editingId === mappingId) {
        resetForm();
      }
    } catch (deleteError: any) {
      setError(deleteError.message || '删除标签映射失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white rounded-3xl border border-[#dadce0] overflow-hidden mt-8">
      <div className="px-6 py-5 border-b border-[#dadce0] flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800 flex items-center gap-2">
            <Icon name="link" size={20} className="text-[#1a73e8]" />
            商品标签映射
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            将模型识别标签映射到库存商品，打通检测结果与库存同步。
          </p>
        </div>
        <span className="text-sm text-slate-500 px-3 py-1 bg-slate-100 rounded-full">已配置 {mappings.length} 条</span>
      </div>

      <div className="p-6 border-b border-[#dadce0] bg-[#f8f9fa]">
        <div className="grid grid-cols-1 md:grid-cols-[1.2fr_1fr_auto] gap-4">
          <input
            type="text"
            value={form.detection_label}
            onChange={(event) =>
              setForm((current) => ({ ...current, detection_label: event.target.value }))
            }
            placeholder="例如：Potato chips"
            className="px-4 py-3 border border-transparent bg-white rounded-xl text-sm focus:ring-1 focus:ring-[#1a73e8] focus:border-[#1a73e8] shadow-sm outline-none transition-all"
          />
          <select
            value={form.item_id}
            onChange={(event) =>
              setForm((current) => ({ ...current, item_id: event.target.value }))
            }
            className="px-4 py-3 border border-transparent bg-white rounded-xl text-sm focus:ring-1 focus:ring-[#1a73e8] focus:border-[#1a73e8] shadow-sm outline-none transition-all cursor-pointer"
          >
            <option value="">选择库存商品</option>
            {itemOptions.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>

          <div className="flex items-center gap-2">
            <motion.button
              whileHover={!saving ? { scale: 1.02 } : {}}
              whileTap={!saving ? { scale: 0.98 } : {}}
              onClick={handleSubmit}
              disabled={saving}
              className="px-5 py-3 bg-[#1a73e8] text-white rounded-full text-sm font-medium hover:bg-[#1557b0] disabled:opacity-50 flex items-center gap-2 transition-colors shadow-sm"
            >
              <Icon name={editingId === null ? "add" : "save"} size={18} />
              {editingId === null ? '新增' : '保存'}
            </motion.button>
            <AnimatePresence>
              {editingId !== null && (
                <motion.button
                  initial={{ opacity: 0, width: 0 }}
                  animate={{ opacity: 1, width: 'auto' }}
                  exit={{ opacity: 0, width: 0 }}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={resetForm}
                  className="px-4 py-3 border border-[#dadce0] bg-white text-slate-700 rounded-full text-sm font-medium hover:bg-slate-50 flex items-center gap-2 transition-colors shadow-sm"
                >
                  <Icon name="close" size={18} />
                  取消
                </motion.button>
              )}
            </AnimatePresence>
          </div>
        </div>

        {error && <p className="text-sm text-[#d93025] font-medium mt-3 ml-1">{error}</p>}
      </div>

      <div className="overflow-x-auto">
        {loading ? (
          <div className="p-8 flex items-center justify-center text-slate-500 gap-2">
             <Icon name="sync" className="animate-spin" />加载标签映射中...
          </div>
        ) : (
          <table className="w-full text-left text-sm text-slate-700">
            <thead className="bg-[#f8f9fa] border-b border-[#dadce0]">
              <tr>
                <th className="px-6 py-4 font-medium text-slate-600 w-1/3">检测标签</th>
                <th className="px-6 py-4 font-medium text-slate-600">映射商品</th>
                <th className="px-6 py-4 font-medium text-slate-600 text-right w-32">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#dadce0]">
              {paginatedMappings.length > 0 ? (
                paginatedMappings.map((mapping) => (
                  <motion.tr 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    key={mapping.id} 
                    className="hover:bg-slate-50 transition-colors group"
                  >
                    <td className="px-6 py-4 font-mono text-slate-900 bg-slate-50 border-r border-[#dadce0]/50">{mapping.detection_label}</td>
                    <td className="px-6 py-4">
                      <span className="font-medium text-slate-800">{mapping.item_name}</span>
                      <span className="text-slate-400 ml-2 font-mono text-xs">({mapping.item_id})</span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <button
                          onClick={() => handleEdit(mapping)}
                          className="p-2 text-slate-400 hover:text-[#1a73e8] hover:bg-[#e8f0fe] rounded-full transition-colors"
                          title="编辑映射"
                        >
                          <Icon name="edit" size={20} />
                        </button>
                        <button
                          onClick={() => handleDelete(mapping.id)}
                          className="p-2 text-slate-400 hover:text-[#d93025] hover:bg-[#fce8e6] rounded-full transition-colors"
                          title="删除映射"
                        >
                          <Icon name="delete" size={20} />
                        </button>
                      </div>
                    </td>
                  </motion.tr>
                ))
              ) : (
                <tr>
                  <td colSpan={3} className="px-6 py-12 text-center text-slate-500">
                    暂无标签映射，请先创建至少一条映射。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex items-center justify-between border-t border-[#dadce0] px-6 py-4 text-sm text-slate-500">
        <div className="flex flex-col gap-1">
          <span>显示 {pageStart}-{pageEnd} 条，共 {mappings.length} 条标签映射</span>
          <span>
            第 {visiblePage} / {visibleTotalPages} 页，每页 {MAPPINGS_PAGE_SIZE} 条
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-slate-100 px-3 py-2 text-slate-600">
            {visiblePage}/{visibleTotalPages}
          </span>
          <button
            onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
            className="rounded-full border border-[#dadce0] px-4 py-2 transition-colors hover:bg-slate-50 disabled:opacity-50"
            disabled={effectiveCurrentPage <= 1 || mappings.length === 0}
          >
            上一页
          </button>
          <button
            onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
            className="rounded-full border border-[#dadce0] px-4 py-2 transition-colors hover:bg-slate-50 disabled:opacity-50"
            disabled={effectiveCurrentPage >= totalPages || mappings.length === 0}
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  );
};
