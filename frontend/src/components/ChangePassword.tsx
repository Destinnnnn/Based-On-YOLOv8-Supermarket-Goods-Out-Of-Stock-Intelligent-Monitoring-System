import React, { useState } from 'react';
import { changePassword } from '../utils/auth';
import { Icon } from './Icon';
import { motion } from 'motion/react';

export function ChangePassword() {
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess(false);

    // 验证新密码
    if (newPassword.length < 8) {
      setError('新密码长度至少为 8 位');
      return;
    }

    if (newPassword !== confirmPassword) {
      setError('两次输入的新密码不一致');
      return;
    }

    setLoading(true);

    try {
      await changePassword(oldPassword, newPassword);
      setSuccess(true);
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');

      // 3 秒后清除成功消息
      setTimeout(() => setSuccess(false), 3000);
    } catch (err: any) {
      setError(err.message || '修改密码失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-md">
      <div className="bg-white rounded-3xl shadow-sm border border-[#dadce0] p-8">
        {error && (
          <div className="mb-6 p-4 bg-[#fce8e6] border border-[#fce8e6] rounded-2xl flex items-start">
            <Icon name="error" size={20} className="text-[#d93025] mr-3 mt-0.5" filled />
            <p className="text-sm text-[#d93025] font-medium leading-relaxed">{error}</p>
          </div>
        )}

        {success && (
          <div className="mb-6 p-4 bg-[#e6f4ea] border border-[#e6f4ea] rounded-2xl flex items-start">
            <Icon name="check_circle" size={20} className="text-[#137333] mr-3 mt-0.5" filled />
            <p className="text-sm text-[#137333] font-medium leading-relaxed">密码修改成功！</p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              当前密码
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <Icon name="lock" size={20} className="text-slate-400" />
              </div>
              <input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                className="block w-full pl-12 pr-4 py-3 bg-slate-50 border border-transparent rounded-xl focus:bg-white focus:ring-1 focus:ring-[#1a73e8] focus:border-[#1a73e8] sm:text-sm outline-none transition-all"
                placeholder="请输入当前密码"
                required
                disabled={loading}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              新密码
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <Icon name="lock" size={20} className="text-slate-400" />
              </div>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="block w-full pl-12 pr-4 py-3 bg-slate-50 border border-transparent rounded-xl focus:bg-white focus:ring-1 focus:ring-[#1a73e8] focus:border-[#1a73e8] sm:text-sm outline-none transition-all"
                placeholder="请输入新密码（至少 8 位）"
                required
                disabled={loading}
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              确认新密码
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                <Icon name="lock" size={20} className="text-slate-400" />
              </div>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="block w-full pl-12 pr-4 py-3 bg-slate-50 border border-transparent rounded-xl focus:bg-white focus:ring-1 focus:ring-[#1a73e8] focus:border-[#1a73e8] sm:text-sm outline-none transition-all"
                placeholder="请再次输入新密码"
                required
                disabled={loading}
              />
            </div>
          </div>

          <motion.button
            whileHover={!loading ? { scale: 1.02 } : {}}
            whileTap={!loading ? { scale: 0.98 } : {}}
            type="submit"
            disabled={loading}
            className="w-full flex justify-center py-3 border border-transparent rounded-full shadow-sm text-sm font-medium text-white bg-[#1a73e8] hover:bg-[#1557b0] outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed mt-4"
          >
            {loading ? '修改中...' : '确认修改'}
          </motion.button>
        </form>
      </div>
    </div>
  );
}
