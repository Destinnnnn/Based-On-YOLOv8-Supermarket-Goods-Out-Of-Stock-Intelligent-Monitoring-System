import { useEffect, useState } from 'react';
import { motion } from 'motion/react';

import { ChangePassword } from '../components/ChangePassword';
import { Icon } from '../components/Icon';
import { authenticatedFetch, getUser, logout } from '../utils/auth';
import { cn } from '../utils/cn';

type SystemSettings = {
  default_item_threshold: number;
  stock_presence_confirmation_frames: number;
  stock_absence_confirmation_frames: number;
  camera_display_name: string;
  camera_location: string;
  camera_default_sync_inventory: boolean;
};

type InventoryResetSummary = {
  items_reset: number;
  detections_deleted: number;
  detection_boxes_deleted: number;
  stock_history_deleted: number;
  alerts_deleted: number;
};

const defaultSettings: SystemSettings = {
  default_item_threshold: 10,
  stock_presence_confirmation_frames: 2,
  stock_absence_confirmation_frames: 3,
  camera_display_name: '本地演示摄像头',
  camera_location: '演示货架区域',
  camera_default_sync_inventory: false,
};

export function SettingsManagement() {
  const [activeTab, setActiveTab] = useState('password');
  const [settingsForm, setSettingsForm] = useState<SystemSettings>(defaultSettings);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [settingsError, setSettingsError] = useState('');
  const [settingsSuccess, setSettingsSuccess] = useState('');
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState('');
  const [resetSuccess, setResetSuccess] = useState('');
  const [resetSummary, setResetSummary] = useState<InventoryResetSummary | null>(null);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const user = getUser();
  const isAdmin = Boolean(user?.is_admin);

  useEffect(() => {
    if (isAdmin) {
      void loadSettings();
    }
  }, [isAdmin]);

  const handleLogout = () => {
    logout();
    window.location.href = '/';
  };

  const loadSettings = async () => {
    try {
      setSettingsLoading(true);
      setSettingsError('');
      const response = await authenticatedFetch('/api/v1/settings');
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '加载系统设置失败');
      }

      const data = await response.json();
      setSettingsForm({
        default_item_threshold: data.default_item_threshold,
        stock_presence_confirmation_frames: data.stock_presence_confirmation_frames,
        stock_absence_confirmation_frames: data.stock_absence_confirmation_frames,
        camera_display_name: data.camera_display_name,
        camera_location: data.camera_location,
        camera_default_sync_inventory: data.camera_default_sync_inventory,
      });
    } catch (error: any) {
      setSettingsError(error.message || '加载系统设置失败');
    } finally {
      setSettingsLoading(false);
    }
  };

  const saveSettings = async () => {
    try {
      setSettingsSaving(true);
      setSettingsError('');
      setSettingsSuccess('');

      const response = await authenticatedFetch('/api/v1/settings', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(settingsForm),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '保存系统设置失败');
      }

      const data = await response.json();
      setSettingsForm({
        default_item_threshold: data.default_item_threshold,
        stock_presence_confirmation_frames: data.stock_presence_confirmation_frames,
        stock_absence_confirmation_frames: data.stock_absence_confirmation_frames,
        camera_display_name: data.camera_display_name,
        camera_location: data.camera_location,
        camera_default_sync_inventory: data.camera_default_sync_inventory,
      });
      setSettingsSuccess('系统设置已保存，并会在本地演示流程中即时生效。');
    } catch (error: any) {
      setSettingsError(error.message || '保存系统设置失败');
    } finally {
      setSettingsSaving(false);
    }
  };

  const resetInventoryState = async () => {
    try {
      setResetLoading(true);
      setResetError('');
      setResetSuccess('');
      setResetSummary(null);

      const response = await authenticatedFetch('/api/v1/inventory/reset-state', {
        method: 'POST',
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || '重置库存状态失败');
      }

      const data = await response.json();
      setResetSummary({
        items_reset: data.items_reset,
        detections_deleted: data.detections_deleted,
        detection_boxes_deleted: data.detection_boxes_deleted,
        stock_history_deleted: data.stock_history_deleted,
        alerts_deleted: data.alerts_deleted,
      });
      setResetSuccess('库存运行状态已重置，商品目录和标签映射已保留。');
      setResetConfirmOpen(false);
    } catch (error: any) {
      setResetError(error.message || '重置库存状态失败');
    } finally {
      setResetLoading(false);
    }
  };

  const updateField = <K extends keyof SystemSettings>(
    field: K,
    value: SystemSettings[K]
  ) => {
    setSettingsForm((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const renderAdminNotice = () => (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
      当前页签需要管理员权限。请使用管理员账号登录后再修改演示配置。
    </div>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="max-w-5xl space-y-6"
    >
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-800">系统设置</h1>
        <p className="mt-1 text-sm text-slate-500">
          管理账号安全、库存演示参数与本地摄像头展示配置。
        </p>
      </div>

      <div className="overflow-hidden rounded-3xl border border-[#dadce0] bg-white md:flex md:min-h-[640px]">
        <div className="w-full space-y-2 border-b border-[#dadce0] bg-[#f8f9fa] p-4 md:w-64 md:border-b-0 md:border-r">
          <button
            onClick={() => setActiveTab('password')}
            className={cn(
              'w-full rounded-full px-4 py-3 text-left text-sm font-medium transition-colors',
              activeTab === 'password'
                ? 'bg-[#e8f0fe] text-[#1a73e8]'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            )}
          >
            <span className="flex items-center gap-3">
              <Icon name="lock" size={20} filled={activeTab === 'password'} />
              修改密码
            </span>
          </button>
          <button
            onClick={() => setActiveTab('alerts')}
            className={cn(
              'w-full rounded-full px-4 py-3 text-left text-sm font-medium transition-colors',
              activeTab === 'alerts'
                ? 'bg-[#e8f0fe] text-[#1a73e8]'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            )}
          >
            <span className="flex items-center gap-3">
              <Icon name="warning" size={20} filled={activeTab === 'alerts'} />
              库存与告警阈值
            </span>
          </button>
          <button
            onClick={() => setActiveTab('camera')}
            className={cn(
              'w-full rounded-full px-4 py-3 text-left text-sm font-medium transition-colors',
              activeTab === 'camera'
                ? 'bg-[#e8f0fe] text-[#1a73e8]'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            )}
          >
            <span className="flex items-center gap-3">
              <Icon name="videocam" size={20} filled={activeTab === 'camera'} />
              演示摄像头配置
            </span>
          </button>
          <button
            onClick={() => setActiveTab('profile')}
            className={cn(
              'w-full rounded-full px-4 py-3 text-left text-sm font-medium transition-colors',
              activeTab === 'profile'
                ? 'bg-[#e8f0fe] text-[#1a73e8]'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            )}
          >
            <span className="flex items-center gap-3">
              <Icon name="person" size={20} filled={activeTab === 'profile'} />
              个人资料
            </span>
          </button>
          <button
            onClick={() => setActiveTab('danger')}
            className={cn(
              'w-full rounded-full px-4 py-3 text-left text-sm font-medium transition-colors',
              activeTab === 'danger'
                ? 'bg-red-50 text-[#d93025]'
                : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
            )}
          >
            <span className="flex items-center gap-3">
              <Icon name="delete" size={20} />
              危险区
            </span>
          </button>
        </div>

        <div className="flex-1 bg-white p-6 md:p-10">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3 }}
            className="space-y-6"
          >
            {(activeTab === 'alerts' || activeTab === 'camera') && (
              <>
                {settingsError && (
                  <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
                    {settingsError}
                  </div>
                )}
                {settingsSuccess && (
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-700">
                    {settingsSuccess}
                  </div>
                )}
              </>
            )}

            {activeTab === 'password' && (
              <div>
                <h2 className="mb-6 text-xl font-bold text-slate-800">修改密码</h2>
                <ChangePassword />
              </div>
            )}

            {activeTab === 'profile' && (
              <div>
                <h2 className="mb-6 text-xl font-bold text-slate-800">个人资料</h2>
                <div className="max-w-md space-y-6">
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">用户名</label>
                    <input
                      type="text"
                      value={user?.username || ''}
                      disabled
                      className="w-full cursor-not-allowed rounded-xl border border-transparent bg-slate-50 px-4 py-3 text-slate-600"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">邮箱</label>
                    <input
                      type="email"
                      value={user?.email || ''}
                      disabled
                      className="w-full cursor-not-allowed rounded-xl border border-transparent bg-slate-50 px-4 py-3 text-slate-600"
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700">角色</label>
                    <input
                      type="text"
                      value={isAdmin ? '管理员' : '普通用户'}
                      disabled
                      className="w-full cursor-not-allowed rounded-xl border border-transparent bg-slate-50 px-4 py-3 text-slate-600"
                    />
                  </div>
                  <div className="border-t border-[#dadce0] pt-6">
                    <motion.button
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      onClick={handleLogout}
                      className="rounded-full bg-[#d93025] px-6 py-2.5 font-medium text-white transition-colors hover:bg-[#b3261e]"
                    >
                      退出登录
                    </motion.button>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'alerts' && (
              <div>
                <h2 className="mb-6 text-xl font-bold text-slate-800">库存与告警阈值</h2>
                {!isAdmin ? (
                  renderAdminNotice()
                ) : settingsLoading ? (
                  <div className="flex items-center gap-2 rounded-2xl border border-[#dadce0] bg-[#f8f9fa] p-5 text-sm text-slate-500">
                    <Icon name="sync" size={18} className="animate-spin" />
                    正在加载系统设置...
                  </div>
                ) : (
                  <div className="max-w-2xl space-y-6 rounded-3xl border border-[#dadce0] bg-white p-6">
                    <div className="space-y-1">
                      <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800">
                        新增商品默认阈值
                      </h3>
                      <p className="text-sm text-slate-500">
                        库存页新增商品时会默认带入这个阈值
                      </p>
                    </div>
                    <input
                      type="number"
                      min="0"
                      value={settingsForm.default_item_threshold}
                      onChange={(event) =>
                        updateField('default_item_threshold', Number(event.target.value))
                      }
                      className="w-40 rounded-xl border border-[#dadce0] px-4 py-3 text-sm outline-none transition-colors focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                    />

                    <div className="h-px bg-[#dadce0]" />

                    <div className="grid gap-6 md:grid-cols-2">
                      <div className="space-y-2">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800">
                          连续出现确认帧
                        </h3>
                        <p className="text-sm text-slate-500">
                          控制检测结果要连续多少帧才把状态从正常切到异常。
                        </p>
                        <input
                          type="number"
                          min="1"
                          value={settingsForm.stock_presence_confirmation_frames}
                          onChange={(event) =>
                            updateField(
                              'stock_presence_confirmation_frames',
                              Number(event.target.value)
                            )
                          }
                          className="w-full rounded-xl border border-[#dadce0] px-4 py-3 text-sm outline-none transition-colors focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                        />
                      </div>
                      <div className="space-y-2">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-slate-800">
                          连续缺失确认帧
                        </h3>
                        <p className="text-sm text-slate-500">
                          控制空帧要连续多少次，才确认商品进入缺货状态。
                        </p>
                        <input
                          type="number"
                          min="1"
                          value={settingsForm.stock_absence_confirmation_frames}
                          onChange={(event) =>
                            updateField(
                              'stock_absence_confirmation_frames',
                              Number(event.target.value)
                            )
                          }
                          className="w-full rounded-xl border border-[#dadce0] px-4 py-3 text-sm outline-none transition-colors focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                        />
                      </div>
                    </div>

                    <div className="flex justify-end pt-2">
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => void saveSettings()}
                        disabled={settingsSaving}
                        className="rounded-full bg-[#1a73e8] px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1557b0] disabled:opacity-60"
                      >
                        {settingsSaving ? '保存中...' : '保存阈值设置'}
                      </motion.button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'camera' && (
              <div>
                <h2 className="mb-6 text-xl font-bold text-slate-800">演示摄像头配置</h2>
                {!isAdmin ? (
                  renderAdminNotice()
                ) : settingsLoading ? (
                  <div className="flex items-center gap-2 rounded-2xl border border-[#dadce0] bg-[#f8f9fa] p-5 text-sm text-slate-500">
                    <Icon name="sync" size={18} className="animate-spin" />
                    正在加载系统设置...
                  </div>
                ) : (
                  <div className="max-w-2xl space-y-6 rounded-3xl border border-[#dadce0] bg-white p-6">
                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700">摄像头展示名称</label>
                      <input
                        type="text"
                        value={settingsForm.camera_display_name}
                        onChange={(event) =>
                          updateField('camera_display_name', event.target.value)
                        }
                        className="w-full rounded-xl border border-[#dadce0] px-4 py-3 text-sm outline-none transition-colors focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                      />
                    </div>

                    <div className="space-y-2">
                      <label className="text-sm font-medium text-slate-700">演示位置说明</label>
                      <input
                        type="text"
                        value={settingsForm.camera_location}
                        onChange={(event) =>
                          updateField('camera_location', event.target.value)
                        }
                        className="w-full rounded-xl border border-[#dadce0] px-4 py-3 text-sm outline-none transition-colors focus:border-[#1a73e8] focus:ring-1 focus:ring-[#1a73e8]"
                      />
                    </div>

                    <div className="rounded-2xl border border-[#dadce0] bg-[#f8f9fa] p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <p className="font-medium text-slate-800">默认同步库存</p>
                          <p className="mt-1 text-sm text-slate-500">
                            实时监控页首次打开时，库存同步开关将默认采用这里的设置。
                          </p>
                        </div>
                        <label className="relative inline-flex cursor-pointer items-center">
                          <input
                            type="checkbox"
                            className="peer sr-only"
                            checked={settingsForm.camera_default_sync_inventory}
                            onChange={(event) =>
                              updateField(
                                'camera_default_sync_inventory',
                                event.target.checked
                              )
                            }
                          />
                          <div className="h-6 w-11 rounded-full bg-slate-300 shadow-sm after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-all after:content-[''] peer-checked:bg-[#1a73e8] peer-checked:after:translate-x-full" />
                        </label>
                      </div>
                    </div>

                    <div className="flex justify-end pt-2">
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => void saveSettings()}
                        disabled={settingsSaving}
                        className="rounded-full bg-[#1a73e8] px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#1557b0] disabled:opacity-60"
                      >
                        {settingsSaving ? '保存中...' : '保存摄像头设置'}
                      </motion.button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'danger' && (
              <div>
                <h2 className="mb-6 text-xl font-bold text-slate-800">危险区</h2>
                {!isAdmin ? (
                  renderAdminNotice()
                ) : (
                  <div className="max-w-2xl space-y-5 rounded-3xl border border-red-200 bg-red-50 p-6">
                    <div className="flex items-start gap-4">
                      <div className="rounded-full bg-white p-3 text-[#d93025]">
                        <Icon name="database" size={24} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <h3 className="text-base font-bold text-slate-900">
                          重置库存运行状态
                        </h3>
                        <p className="mt-2 text-sm leading-6 text-slate-600">
                          将清空检测记录、检测框、库存历史和告警记录，并把所有商品库存重置为 0、状态重置为缺货。商品目录、标签映射、账号和系统设置不会被删除。
                        </p>
                      </div>
                    </div>

                    {resetError && (
                      <div className="rounded-2xl border border-red-200 bg-white px-4 py-3 text-sm font-medium text-red-700">
                        {resetError}
                      </div>
                    )}
                    {resetSuccess && (
                      <div className="rounded-2xl border border-emerald-200 bg-white px-4 py-3 text-sm font-medium text-emerald-700">
                        {resetSuccess}
                      </div>
                    )}
                    {resetSummary && (
                      <div className="grid gap-3 text-sm text-slate-600 sm:grid-cols-2">
                        <div className="rounded-2xl bg-white px-4 py-3">
                          重置商品：{resetSummary.items_reset}
                        </div>
                        <div className="rounded-2xl bg-white px-4 py-3">
                          删除检测记录：{resetSummary.detections_deleted}
                        </div>
                        <div className="rounded-2xl bg-white px-4 py-3">
                          删除检测框：{resetSummary.detection_boxes_deleted}
                        </div>
                        <div className="rounded-2xl bg-white px-4 py-3">
                          删除库存历史：{resetSummary.stock_history_deleted}
                        </div>
                        <div className="rounded-2xl bg-white px-4 py-3 sm:col-span-2">
                          删除告警记录：{resetSummary.alerts_deleted}
                        </div>
                      </div>
                    )}

                    <div className="flex justify-end">
                      <motion.button
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                        onClick={() => {
                          setResetError('');
                          setResetSuccess('');
                          setResetConfirmOpen(true);
                        }}
                        disabled={resetLoading}
                        className="rounded-full bg-[#d93025] px-6 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#b3261e] disabled:opacity-60"
                      >
                        {resetLoading ? '重置中...' : '一键重置库存状态'}
                      </motion.button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </motion.div>
        </div>
      </div>

      {resetConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 px-4">
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            className="w-full max-w-md rounded-3xl bg-white p-6 shadow-xl"
          >
            <div className="flex items-start gap-4">
              <div className="rounded-full bg-red-50 p-3 text-[#d93025]">
                <Icon name="warning" size={24} />
              </div>
              <div>
                <h3 className="text-lg font-bold text-slate-900">确认重置库存状态？</h3>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  此操作会清空运行记录并把所有商品设为缺货，适合重新开始演示。商品基础资料和标签映射会保留。
                </p>
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setResetConfirmOpen(false)}
                disabled={resetLoading}
                className="rounded-full border border-[#dadce0] px-5 py-2.5 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-60"
              >
                取消
              </button>
              <motion.button
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
                type="button"
                onClick={() => void resetInventoryState()}
                disabled={resetLoading}
                className="rounded-full bg-[#d93025] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#b3261e] disabled:opacity-60"
              >
                {resetLoading ? '重置中...' : '确认重置'}
              </motion.button>
            </div>
          </motion.div>
        </div>
      )}
    </motion.div>
  );
}
