import React, { useState } from 'react';
import { motion } from 'motion/react';
import { API_URL } from '../utils/auth';
import { Icon } from '../components/Icon';

export function Login({ onLogin }: { onLogin: () => void }) {
  const [isRegisterMode, setIsRegisterMode] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isRegisterMode) {
        if (password !== confirmPassword) {
          throw new Error('两次输入的密码不一致');
        }
        if (password.length < 8) {
          throw new Error('密码至少需要8位字符');
        }

        const response = await fetch(`${API_URL}/api/v1/auth/register`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username,
            email,
            password,
          }),
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.detail || '注册失败');
        }

        setIsRegisterMode(false);
        setError('');
        alert('注册成功！请登录');
      } else {
        const formData = new URLSearchParams();
        formData.set('username', username);
        formData.set('password', password);

        const response = await fetch(`${API_URL}/api/v1/auth/login`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: formData,
        });

        if (!response.ok) {
          let detail = '登录失败';
          try {
            const data = await response.json();
            detail = data.detail || detail;
          } catch {
            if (response.status >= 500) {
              detail = '后端服务异常，请检查本地数据库和后端日志';
            }
          }
          throw new Error(detail);
        }

        const data = await response.json();

        localStorage.setItem('access_token', data.access_token);
        localStorage.setItem('token_type', data.token_type);

        const userResponse = await fetch(`${API_URL}/api/v1/auth/me`, {
          headers: {
            'Authorization': `Bearer ${data.access_token}`,
          },
        });

        if (userResponse.ok) {
          const userData = await userResponse.json();
          localStorage.setItem('user', JSON.stringify(userData));
        }

        onLogin();
      }
    } catch (err: any) {
      const fallbackMessage = isRegisterMode
        ? '注册失败，请稍后重试'
        : '登录失败，请检查后端服务是否已启动';
      if (err instanceof TypeError && /fetch/i.test(err.message || '')) {
        setError('无法连接后端服务，请确认项目已正常启动');
      } else {
        setError(err.message || fallbackMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f8f9fa] flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.4, 0, 0.2, 1] }}
        className="max-w-[450px] w-full bg-white rounded-[24px] overflow-hidden border border-[#dadce0] shadow-sm"
      >
        <div className="px-10 pt-12 pb-10">
          <div className="flex justify-center mb-4">
            <div className="flex items-center justify-center text-[#1a73e8]">
              <Icon name="camera" size={48} filled />
            </div>
          </div>

          <div className="text-center mb-8">
            <h1 className="text-2xl font-normal text-[#202124]">
              {isRegisterMode ? '创建您的 Cam 账号' : '登录'}
            </h1>
            <p className="text-[#5f6368] mt-3 font-medium">使用您的智能监测账号</p>
          </div>

          {error && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mb-6 p-3 flex items-center gap-2 text-[#d93025]">
               <Icon name="error" size={20} filled />
              <p className="text-sm font-medium">{error}</p>
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4 text-left">
            <div>
              <div className="relative group">
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  className="block w-full px-4 pt-6 pb-2 border border-[#dadce0] rounded-[4px] focus:ring-2 focus:ring-[#1a73e8]/20 focus:border-[#1a73e8] text-[16px] text-[#202124] transition-all peer outline-none hover:bg-[#f1f3f4]/50 focus:hover:bg-transparent"
                  placeholder=" "
                  required
                  disabled={loading}
                />
                <label className="absolute text-[16px] text-[#5f6368] duration-200 transform -translate-y-3 scale-75 top-4 z-10 origin-[0] left-4 peer-placeholder-shown:scale-100 peer-placeholder-shown:translate-y-0 peer-focus:scale-75 peer-focus:-translate-y-3 peer-focus:text-[#1a73e8]">
                  用户名
                </label>
              </div>
            </div>

            {isRegisterMode && (
              <div>
                <div className="relative group">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="block w-full px-4 pt-6 pb-2 border border-[#dadce0] rounded-[4px] focus:ring-2 focus:ring-[#1a73e8]/20 focus:border-[#1a73e8] text-[16px] text-[#202124] transition-all peer outline-none hover:bg-[#f1f3f4]/50 focus:hover:bg-transparent"
                    placeholder=" "
                    required={isRegisterMode}
                    disabled={loading}
                  />
                  <label className="absolute text-[16px] text-[#5f6368] duration-200 transform -translate-y-3 scale-75 top-4 z-10 origin-[0] left-4 peer-placeholder-shown:scale-100 peer-placeholder-shown:translate-y-0 peer-focus:scale-75 peer-focus:-translate-y-3 peer-focus:text-[#1a73e8]">
                    邮箱地址
                  </label>
                </div>
              </div>
            )}

            <div>
              <div className="relative group">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={isRegisterMode ? 'new-password' : 'current-password'}
                  className="block w-full px-4 pt-6 pb-2 border border-[#dadce0] rounded-[4px] focus:ring-2 focus:ring-[#1a73e8]/20 focus:border-[#1a73e8] text-[16px] text-[#202124] transition-all peer outline-none hover:bg-[#f1f3f4]/50 focus:hover:bg-transparent"
                  placeholder=" "
                  required
                  disabled={loading}
                />
                <label className="absolute text-[16px] text-[#5f6368] duration-200 transform -translate-y-3 scale-75 top-4 z-10 origin-[0] left-4 peer-placeholder-shown:scale-100 peer-placeholder-shown:translate-y-0 peer-focus:scale-75 peer-focus:-translate-y-3 peer-focus:text-[#1a73e8]">
                  输入您的密码
                </label>
              </div>
            </div>

            {isRegisterMode && (
              <div>
                <div className="relative group">
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    autoComplete="new-password"
                    className="block w-full px-4 pt-6 pb-2 border border-[#dadce0] rounded-[4px] focus:ring-2 focus:ring-[#1a73e8]/20 focus:border-[#1a73e8] text-[16px] text-[#202124] transition-all peer outline-none hover:bg-[#f1f3f4]/50 focus:hover:bg-transparent"
                    placeholder=" "
                    required={isRegisterMode}
                    disabled={loading}
                  />
                  <label className="absolute text-[16px] text-[#5f6368] duration-200 transform -translate-y-3 scale-75 top-4 z-10 origin-[0] left-4 peer-placeholder-shown:scale-100 peer-placeholder-shown:translate-y-0 peer-focus:scale-75 peer-focus:-translate-y-3 peer-focus:text-[#1a73e8]">
                    确认您的密码
                  </label>
                </div>
              </div>
            )}

            {!isRegisterMode && (
              <div className="flex items-center pt-2">
                 <input
                    id="remember-me"
                    type="checkbox"
                    className="h-4 w-4 text-[#1a73e8] focus:ring-[#1a73e8] border-[#dadce0] rounded"
                  />
                  <label htmlFor="remember-me" className="ml-2 block text-[14px] text-[#202124]">
                    在这台设备上记住我
                  </label>
              </div>
            )}

            <div className="pt-8 flex items-center justify-between">
              <button
                type="button"
                onClick={() => {
                  setIsRegisterMode(!isRegisterMode);
                  setError('');
                  setEmail('');
                  setConfirmPassword('');
                  setUsername('');
                  setPassword('');
                }}
                className="text-[14px] font-medium text-[#1a73e8] hover:bg-[#f8f9fa] px-2 py-1.5 -ml-2 rounded transition-colors"
                disabled={loading}
              >
                {isRegisterMode ? '改为登录' : '创建账号'}
              </button>

              <motion.button
                whileTap={{ scale: 0.95 }}
                type="submit"
                disabled={loading}
                className="px-6 py-2 rounded-full text-[14px] font-medium text-white bg-[#1a73e8] hover:bg-[#1b66c9] hover:shadow-md focus:outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (isRegisterMode ? '请稍候...' : '正在登录...') : '下一步'}
              </motion.button>
            </div>
          </form>
        </div>
      </motion.div>
    </div>
  );
}
