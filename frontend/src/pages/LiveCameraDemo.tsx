import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'motion/react';

import { Icon } from '../components/Icon';
import { buildAuthenticatedWebSocketUrl, authenticatedFetch } from '../utils/auth';
import { cn } from '../utils/cn';

type DetectionBox = {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  confidence: number;
  class_id?: number;
  predicted_count?: number;
  count_confidence?: number | null;
  count_model_version?: string | null;
};

type RenderBox = DetectionBox & {
  left: number;
  top: number;
  width: number;
  height: number;
};

type SocketState = 'idle' | 'connecting' | 'connected' | 'error';
type SourceMode = 'idle' | 'camera' | 'video' | 'demo';

type PendingUpdate = {
  item_id: string;
  item_name: string;
  status: string;
  frames_seen: number;
  frames_required: number;
};

type SyncResult = {
  updated_items: number;
  status_changes: number;
  pending_status_count?: number;
  pending_updates?: PendingUpdate[];
  detection_counts?: Record<string, number>;
  matched_labels: string[];
  unmatched_labels?: string[];
  message?: string;
} | null;

const DETECTION_INTERVAL_MS = 4000;
const DEMO_FRAME_INTERVAL_MS = 800;
const RETRY_CAPTURE_DELAY_MS = 500;
const DEMO_CAMERA_ID = 'demo_dataset';
const ZERO_DETECTION_HINT =
  '未检测到训练类别商品，请用饮料、薯片、饼干、洗发水、牙膏、储物盒等训练类别商品测试。';

function resolvePredictedCount(box: DetectionBox) {
  const count = Number(box.predicted_count ?? 1);
  if (!Number.isFinite(count) || count < 1) {
    return 1;
  }
  return Math.round(count);
}

export function LiveCameraDemo() {
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const [sourceMode, setSourceMode] = useState<SourceMode>('idle');
  const [isUsingCamera, setIsUsingCamera] = useState(false);
  const [demoImageSrc, setDemoImageSrc] = useState<string | null>(null);
  const [demoImageName, setDemoImageName] = useState('');
  const [demoFrameKind, setDemoFrameKind] = useState('');
  const [demoFrameIndex, setDemoFrameIndex] = useState<number | null>(null);
  const [demoFrameCount, setDemoFrameCount] = useState<number | null>(null);
  const [demoCachedDetection, setDemoCachedDetection] = useState(false);
  const [boxes, setBoxes] = useState<DetectionBox[]>([]);
  const [socketState, setSocketState] = useState<SocketState>('idle');
  const [statusText, setStatusText] = useState('等待接入摄像头或本地视频');
  const [syncInventory, setSyncInventory] = useState(false);
  const [syncResult, setSyncResult] = useState<SyncResult>(null);
  const [lastDetectionAt, setLastDetectionAt] = useState('');
  const [layoutVersion, setLayoutVersion] = useState(0);
  const [cameraDisplayName, setCameraDisplayName] = useState('本地演示摄像头');
  const [cameraLocation, setCameraLocation] = useState('演示货架区域');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const demoImageRef = useRef<HTMLImageElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const captureTimerRef = useRef<number | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const manualCloseRef = useRef(false);
  const sendCurrentFrameRef = useRef<() => boolean>(() => false);
  const frameInFlightRef = useRef(false);
  const zeroDetectionStreakRef = useRef(0);
  const demoSessionStartedRef = useRef(false);

  const isDemoMode = sourceMode === 'demo';
  const hasVideoSource = sourceMode === 'camera' || sourceMode === 'video' || isDemoMode;

  const cameraWsUrl = useMemo(() => {
    return buildAuthenticatedWebSocketUrl('/api/v1/camera/stream');
  }, []);

  const totalPredictedCount = useMemo(() => {
    return boxes.reduce((total, box) => total + resolvePredictedCount(box), 0);
  }, [boxes]);

  const syncedItemCounts = useMemo(() => {
    return Object.entries(syncResult?.detection_counts ?? {});
  }, [syncResult]);

  const bumpLayout = useCallback(() => {
    setLayoutVersion((value) => value + 1);
  }, []);

  const playVideoElement = useCallback(async () => {
    const video = videoRef.current;
    if (!video) {
      return;
    }

    try {
      await video.play();
      bumpLayout();
    } catch (error) {
      console.error('Video playback failed:', error);
    }
  }, [bumpLayout]);

  const clearCaptureTimer = useCallback(() => {
    if (captureTimerRef.current !== null) {
      window.clearTimeout(captureTimerRef.current);
      captureTimerRef.current = null;
    }
  }, []);

  const clearUploadedVideo = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setVideoSrc(null);
  }, []);

  const clearDemoFrame = useCallback(() => {
    setDemoImageSrc(null);
    setDemoImageName('');
    setDemoFrameKind('');
    setDemoFrameIndex(null);
    setDemoFrameCount(null);
    setDemoCachedDetection(false);
    demoSessionStartedRef.current = false;
  }, []);

  const stopCamera = useCallback(() => {
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    }

    if (videoRef.current?.srcObject) {
      videoRef.current.srcObject = null;
    }
    setIsUsingCamera(false);
  }, []);

  const closeSocket = useCallback((nextStatus?: string) => {
    manualCloseRef.current = true;
    clearCaptureTimer();
    frameInFlightRef.current = false;

    const socket = socketRef.current;
    socketRef.current = null;

    if (
      socket &&
      (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
    ) {
      socket.close();
    }

    setSocketState('idle');
    if (nextStatus) {
      setStatusText(nextStatus);
    }
  }, [clearCaptureTimer]);

  const scheduleNextCapture = useCallback((delay = DETECTION_INTERVAL_MS) => {
    clearCaptureTimer();

    const trySendFrame = () => {
      captureTimerRef.current = null;
      const sent = sendCurrentFrameRef.current();

      if (
        !sent &&
        !frameInFlightRef.current &&
        socketRef.current?.readyState === WebSocket.OPEN
      ) {
        captureTimerRef.current = window.setTimeout(
          trySendFrame,
          RETRY_CAPTURE_DELAY_MS
        );
      }
    };

    captureTimerRef.current = window.setTimeout(trySendFrame, delay);
  }, [clearCaptureTimer]);

  const stopPreview = useCallback(() => {
    stopCamera();
    clearUploadedVideo();
    clearDemoFrame();
    setSourceMode('idle');
    closeSocket('已停止预览');
    setBoxes([]);
    setSyncResult(null);
    setLastDetectionAt('');
  }, [clearDemoFrame, clearUploadedVideo, closeSocket, stopCamera]);

  const connectSocket = useCallback(() => {
    manualCloseRef.current = false;
    clearCaptureTimer();

    const currentSocket = socketRef.current;
    if (
      currentSocket &&
      (currentSocket.readyState === WebSocket.OPEN ||
        currentSocket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    setSocketState('connecting');
    setStatusText('正在连接后端识别服务...');

    const socket = new WebSocket(cameraWsUrl);
    socketRef.current = socket;

    socket.onopen = () => {
      setSocketState('connected');
      frameInFlightRef.current = false;
      zeroDetectionStreakRef.current = 0;
      setStatusText(
        syncInventory
          ? '后端已连接，识别结果将尝试同步库存'
          : '后端已连接，当前为实时识别预览模式'
      );
      scheduleNextCapture(0);
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type !== 'detection') {
          return;
        }

        frameInFlightRef.current = false;
        const nextBoxes = Array.isArray(data.boxes) ? data.boxes : [];
        const detectedItemTotal =
          typeof data.total_predicted_count === 'number'
            ? data.total_predicted_count
            : nextBoxes.reduce(
                (total: number, box: DetectionBox) => total + resolvePredictedCount(box),
                0
              );
        setBoxes(nextBoxes);
        setSyncResult(data.sync_result ?? null);
        setLastDetectionAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }));
        if (data.image) {
          setDemoImageSrc(data.image);
          setDemoImageName(data.image_name || '');
          setDemoFrameKind(data.demo_frame_kind || '');
          setDemoFrameIndex(typeof data.frame_index === 'number' ? data.frame_index : null);
          setDemoFrameCount(
            typeof data.demo_frame_count === 'number' ? data.demo_frame_count : null
          );
          setDemoCachedDetection(Boolean(data.cached_detection));
          bumpLayout();
        }

        if (nextBoxes.length === 0) {
          zeroDetectionStreakRef.current += 1;
        } else {
          zeroDetectionStreakRef.current = 0;
        }

        const processingText =
          typeof data.processing_ms === 'number'
            ? `，后端耗时 ${(data.processing_ms / 1000).toFixed(1)} 秒`
            : '';
        const zeroDetectionText =
          zeroDetectionStreakRef.current > 0 ? `；${ZERO_DETECTION_HINT}` : '';

        if (data.sync_inventory) {
          if (data.sync_result?.message) {
            setStatusText(
              `已识别 ${data.count} 个目标，估计 ${detectedItemTotal} 件${processingText}；${data.sync_result.message}${zeroDetectionText}`
            );
          } else {
            setStatusText(
              `已识别 ${data.count} 个目标，估计 ${detectedItemTotal} 件${processingText}，并完成库存同步。${zeroDetectionText}`
            );
          }
        } else {
          setStatusText(
            `已识别 ${data.count} 个目标，估计 ${detectedItemTotal} 件${processingText}（仅预览，不写入库存）${zeroDetectionText}`
          );
        }
        scheduleNextCapture(isDemoMode ? DEMO_FRAME_INTERVAL_MS : DETECTION_INTERVAL_MS);
      } catch (error) {
        frameInFlightRef.current = false;
        console.error('Failed to parse camera websocket message:', error);
        scheduleNextCapture(isDemoMode ? DEMO_FRAME_INTERVAL_MS : DETECTION_INTERVAL_MS);
      }
    };

    socket.onerror = () => {
      frameInFlightRef.current = false;
      clearCaptureTimer();
      setSocketState('error');
      setStatusText('与后端 WebSocket 连接失败');
    };

    socket.onclose = () => {
      frameInFlightRef.current = false;
      clearCaptureTimer();
      if (manualCloseRef.current) {
        return;
      }
      setSocketState('error');
      setStatusText('与后端识别服务的连接已断开');
    };
  }, [bumpLayout, cameraWsUrl, clearCaptureTimer, isDemoMode, scheduleNextCapture, syncInventory]);

  const sendCurrentFrame = useCallback(() => {
    const socket = socketRef.current;
    const video = videoRef.current;

    if (
      frameInFlightRef.current ||
      !socket ||
      socket.readyState !== WebSocket.OPEN
    ) {
      return false;
    }

    if (isDemoMode) {
      frameInFlightRef.current = true;
      setStatusText('正在读取测试集图片帧并联动后端识别...');

      socket.send(
        JSON.stringify({
          type: 'demo_frame',
          source: 'test',
          reset: !demoSessionStartedRef.current,
          sync_inventory: syncInventory,
          camera_id: DEMO_CAMERA_ID,
          max_images: 20,
          repeat_min: 5,
          repeat_max: 10,
          empty_interval: 5,
          empty_frames: 3,
        })
      );
      demoSessionStartedRef.current = true;
      return true;
    }

    if (!video) {
      return false;
    }

    if (
      video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA ||
      !video.videoWidth ||
      !video.videoHeight
    ) {
      return false;
    }

    const canvas = canvasRef.current ?? document.createElement('canvas');
    canvasRef.current = canvas;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;

    const context = canvas.getContext('2d');
    if (!context) {
      return false;
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const image = canvas.toDataURL('image/jpeg', 0.75);

    frameInFlightRef.current = true;
    setStatusText('正在识别当前画面，上一帧返回后才会发送下一帧...');

    socket.send(
      JSON.stringify({
        type: 'frame',
        image,
        sync_inventory: syncInventory,
        camera_id: sourceMode === 'video' ? 'local_video' : 'camera_1',
      })
    );
    return true;
  }, [isDemoMode, sourceMode, syncInventory]);

  useEffect(() => {
    sendCurrentFrameRef.current = sendCurrentFrame;
  }, [sendCurrentFrame]);

  const startCamera = useCallback(async () => {
    try {
      stopCamera();
      clearUploadedVideo();
      clearDemoFrame();

      const mediaStream = await navigator.mediaDevices.getUserMedia({ video: true });
      cameraStreamRef.current = mediaStream;

      setIsUsingCamera(true);
      setSourceMode('camera');
      setBoxes([]);
      setSyncResult(null);
      setStatusText('摄像头已打开，正在连接后端...');
      bumpLayout();
    } catch (error) {
      console.error('Error accessing camera:', error);
      alert('无法访问摄像头，请检查浏览器权限或设备是否被占用。');
    }
  }, [bumpLayout, clearDemoFrame, clearUploadedVideo, stopCamera]);

  const handleVideoUpload = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    stopCamera();
    clearUploadedVideo();
    clearDemoFrame();

    const url = URL.createObjectURL(file);
    objectUrlRef.current = url;
    setVideoSrc(url);
    setSourceMode('video');
    setBoxes([]);
    setSyncResult(null);
    setStatusText(`已加载本地视频：${file.name}`);
    bumpLayout();

    event.target.value = '';
  }, [bumpLayout, clearDemoFrame, clearUploadedVideo, stopCamera]);

  const startDatasetDemo = useCallback(() => {
    stopCamera();
    clearUploadedVideo();
    clearDemoFrame();
    setSourceMode('demo');
    setSyncInventory(true);
    setBoxes([]);
    setSyncResult(null);
    setLastDetectionAt('');
    setStatusText('正在启动测试集图片演示源...');
    bumpLayout();
  }, [bumpLayout, clearDemoFrame, clearUploadedVideo, stopCamera]);

  const handleFullscreen = useCallback(async () => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }

    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else if (stage.requestFullscreen) {
        await stage.requestFullscreen();
      }
      bumpLayout();
    } catch (error) {
      console.error('Fullscreen request failed:', error);
    }
  }, [bumpLayout]);

  useEffect(() => {
    let active = true;

    const loadCameraSettings = async () => {
      try {
        const response = await authenticatedFetch('/api/v1/settings');
        if (!response.ok) {
          return;
        }

        const data = await response.json();
        if (!active) {
          return;
        }

        setCameraDisplayName(data.camera_display_name);
        setCameraLocation(data.camera_location);
        setSyncInventory(Boolean(data.camera_default_sync_inventory));
      } catch (error) {
        console.error('Error loading camera settings:', error);
      }
    };

    void loadCameraSettings();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!isUsingCamera || !video || !cameraStreamRef.current) {
      return;
    }

    if (video.srcObject !== cameraStreamRef.current) {
      video.srcObject = cameraStreamRef.current;
      video.muted = true;
    }

    void playVideoElement();
  }, [isUsingCamera, layoutVersion, playVideoElement]);

  useEffect(() => {
    if (!hasVideoSource) {
      closeSocket('等待接入摄像头、本地视频或数据集演示源');
      setBoxes([]);
      setSyncResult(null);
      return;
    }

    connectSocket();

    return () => {
      closeSocket();
    };
  }, [closeSocket, connectSocket, hasVideoSource]);

  useEffect(() => {
    if (socketState !== 'connected' || !hasVideoSource) {
      clearCaptureTimer();
      frameInFlightRef.current = false;
      return;
    }

    scheduleNextCapture(0);

    return () => {
      clearCaptureTimer();
    };
  }, [clearCaptureTimer, hasVideoSource, scheduleNextCapture, socketState]);

  useEffect(() => {
    const handleResize = () => bumpLayout();

    window.addEventListener('resize', handleResize);
    document.addEventListener('fullscreenchange', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      document.removeEventListener('fullscreenchange', handleResize);
    };
  }, [bumpLayout]);

  useEffect(() => {
    const stage = stageRef.current;
    const video = videoRef.current;
    const demoImage = demoImageRef.current;

    if (typeof ResizeObserver === 'undefined' || (!stage && !video && !demoImage)) {
      return;
    }

    const observer = new ResizeObserver(() => bumpLayout());
    if (stage) {
      observer.observe(stage);
    }
    if (video) {
      observer.observe(video);
    }
    if (demoImage) {
      observer.observe(demoImage);
    }

    return () => observer.disconnect();
  }, [bumpLayout, demoImageSrc, hasVideoSource]);

  useEffect(() => {
    return () => {
      stopPreview();
    };
  }, [stopPreview]);

  const renderedBoxes = useMemo<RenderBox[]>(() => {
    const stage = stageRef.current;
    const video = videoRef.current;
    const demoImage = demoImageRef.current;
    const mediaElement = isDemoMode ? demoImage : video;
    const naturalWidth = isDemoMode ? demoImage?.naturalWidth : video?.videoWidth;
    const naturalHeight = isDemoMode ? demoImage?.naturalHeight : video?.videoHeight;

    if (!stage || !mediaElement || !boxes.length || !naturalWidth || !naturalHeight) {
      return [];
    }

    const stageRect = stage.getBoundingClientRect();
    const mediaRect = mediaElement.getBoundingClientRect();

    if (!stageRect.width || !stageRect.height || !mediaRect.width || !mediaRect.height) {
      return [];
    }

    const offsetLeft = mediaRect.left - stageRect.left;
    const offsetTop = mediaRect.top - stageRect.top;
    const scaleX = mediaRect.width / naturalWidth;
    const scaleY = mediaRect.height / naturalHeight;

    return boxes.map((box) => ({
      ...box,
      left: offsetLeft + box.x * scaleX,
      top: offsetTop + box.y * scaleY,
      width: box.w * scaleX,
      height: box.h * scaleY,
    }));
  }, [boxes, demoImageSrc, isDemoMode, layoutVersion]);

  const socketStateBadge = {
    idle: { icon: 'wifi_off', label: '未连接', className: 'text-slate-300' },
    connecting: { icon: 'cable', label: '连接中', className: 'text-amber-300' },
    connected: { icon: 'wifi', label: '已连接', className: 'text-emerald-300' },
    error: { icon: 'wifi_off', label: '连接异常', className: 'text-red-300' },
  }[socketState];

  const sourceLabel =
    sourceMode === 'camera'
      ? '本机摄像头'
      : sourceMode === 'video'
        ? '本地视频'
        : sourceMode === 'demo'
          ? '数据集演示'
          : '等待输入';

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="flex h-full flex-col space-y-6"
    >
      <div className="flex flex-col justify-between gap-4 xl:flex-row xl:items-center">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-800">实时视频监控</h1>
          <p className="mt-1 text-sm text-slate-500">
            {cameraDisplayName} · {cameraLocation}
          </p>
          <p className="mt-2 text-sm text-slate-500">
            可接入摄像头、本地视频或测试集图片流，后端完成 YOLOv8 检测后实时回传框选结果并同步库存。
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={startCamera}
            className="flex items-center gap-2 rounded-full bg-[#1a73e8] px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[#1557b0]"
          >
            <Icon name="videocam" size={18} />
            调用本机摄像头
          </motion.button>

          <input
            type="file"
            accept="video/*"
            className="hidden"
            ref={fileInputRef}
            onChange={handleVideoUpload}
          />

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-2 rounded-full bg-[#e8f0fe] px-4 py-2 text-sm font-medium text-[#1a73e8] shadow-sm transition-colors hover:bg-[#d2e3fc]"
          >
            <Icon name="upload" size={18} />
            导入本地视频
          </motion.button>

          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={startDatasetDemo}
            className="flex items-center gap-2 rounded-full bg-[#e6f4ea] px-4 py-2 text-sm font-medium text-[#137333] shadow-sm transition-colors hover:bg-[#ceead6]"
          >
            <Icon name="smart_display" size={18} />
            数据集演示
          </motion.button>

          <motion.button
            whileHover={hasVideoSource ? { scale: 1.02 } : {}}
            whileTap={hasVideoSource ? { scale: 0.98 } : {}}
            onClick={stopPreview}
            disabled={!hasVideoSource}
            className="flex items-center gap-2 rounded-full border border-[#dadce0] bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Icon name="stop" size={18} />
            停止预览
          </motion.button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <motion.div
          layout
          ref={stageRef}
          className="relative flex min-h-[480px] w-full items-center justify-center overflow-hidden rounded-3xl border border-[#dadce0] bg-[#202124] shadow-md"
        >
          <div className="absolute left-4 top-4 z-10 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border border-white/20 bg-[#202124]/70 px-4 py-1.5 text-sm font-medium text-white backdrop-blur-md">
              <div className={cn('h-2 w-2 rounded-full', hasVideoSource ? 'animate-pulse bg-red-500' : 'bg-slate-500')} />
              {sourceLabel}
            </div>

            <div
              className={cn(
                'flex items-center gap-2 rounded-full border border-white/20 bg-[#202124]/70 px-4 py-1.5 text-sm font-medium backdrop-blur-md',
                socketStateBadge.className
              )}
            >
              <Icon name={socketStateBadge.icon} size={16} />
              {socketStateBadge.label}
            </div>

            <div className="rounded-full border border-white/20 bg-[#202124]/70 px-4 py-1.5 font-mono text-sm text-white backdrop-blur-md">
              检测框 {boxes.length} 个
            </div>

            <div className="rounded-full border border-white/20 bg-[#202124]/70 px-4 py-1.5 font-mono text-sm text-white backdrop-blur-md">
              估计 {totalPredictedCount} 件
            </div>
          </div>

          <div className="absolute right-4 top-4 z-10">
            <button
              onClick={handleFullscreen}
              className="rounded-full border border-white/20 bg-[#202124]/70 p-2 text-white transition-colors hover:bg-white/20"
              title="全屏"
            >
              <Icon name="fullscreen" size={20} />
            </button>
          </div>

          {!hasVideoSource ? (
            <div className="flex flex-1 flex-col items-center justify-center px-6 text-center text-slate-400">
              <Icon name="videocam_off" size={64} className="mb-4 opacity-20" />
              <p className="text-lg font-medium">暂无视频源</p>
              <p className="mt-1 text-sm">
                请点击上方按钮调用本机摄像头、导入本地视频，或启动数据集演示。
              </p>
            </div>
          ) : (
            <div className="relative flex h-full w-full items-center justify-center">
              {isDemoMode ? (
                demoImageSrc ? (
                  <img
                    ref={demoImageRef}
                    src={demoImageSrc}
                    alt="数据集演示帧"
                    className="h-auto max-h-full w-auto max-w-full rounded-xl"
                    onLoad={bumpLayout}
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center text-slate-400">
                    <Icon name="hourglass_top" size={48} className="mb-3 opacity-30" />
                    <p className="text-sm">正在等待第一帧测试集图片...</p>
                  </div>
                )
              ) : (
                <video
                  ref={videoRef}
                  src={videoSrc || undefined}
                  className="h-auto max-h-full w-auto max-w-full rounded-xl"
                  autoPlay
                  loop
                  muted
                  playsInline
                  onLoadedData={() => {
                    bumpLayout();
                    void playVideoElement();
                  }}
                  onCanPlay={() => {
                    bumpLayout();
                    void playVideoElement();
                  }}
                  onLoadedMetadata={() => {
                    bumpLayout();
                    void playVideoElement();
                  }}
                  onPlay={bumpLayout}
                />
              )}

              <div className="pointer-events-none absolute inset-0">
                {renderedBoxes.map((box, index) => {
                  const highlightClass =
                    box.confidence >= 0.6
                      ? 'border-[#34a853] text-[#34a853] bg-[#34a853]/10'
                      : 'border-[#fbbc04] text-[#fbbc04] bg-[#fbbc04]/10';

                  return (
                    <motion.div
                      layout
                      key={`${box.label}-${index}-${box.left}-${box.top}`}
                      className={cn('absolute rounded-lg border-2 transition-all duration-300', highlightClass)}
                      style={{
                        left: `${box.left}px`,
                        top: `${box.top}px`,
                        width: `${box.width}px`,
                        height: `${box.height}px`,
                      }}
                    >
                      <div
                        className={cn(
                          'absolute left-[-2px] -top-7 whitespace-nowrap rounded border-2 bg-white px-2 py-0.5 text-xs font-semibold',
                          highlightClass
                        )}
                      >
                        {box.label} {Math.round(box.confidence * 100)}% ×{resolvePredictedCount(box)}
                      </div>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          )}
        </motion.div>

        <motion.div
          layout
          className="flex flex-col gap-6 overflow-y-auto rounded-3xl border border-[#dadce0] bg-white p-6"
        >
          <div>
            <h2 className="text-lg font-bold text-slate-800">联调状态</h2>
            <p className="mt-1 text-sm text-slate-500">{statusText}</p>
          </div>

          {isDemoMode && (
            <div className="space-y-3 rounded-2xl border border-[#ceead6] bg-[#f6fff8] p-5">
              <p className="flex items-center gap-2 font-medium text-[#137333]">
                <Icon name="smart_display" size={18} filled />
                测试集图片流
              </p>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-xl border border-[#ceead6] bg-white p-3">
                  <p className="text-xs text-slate-500">当前帧</p>
                  <p className="mt-1 truncate font-semibold text-slate-800">
                    {demoImageName || '等待中'}
                  </p>
                </div>
                <div className="rounded-xl border border-[#ceead6] bg-white p-3">
                  <p className="text-xs text-slate-500">帧序号</p>
                  <p className="mt-1 font-mono font-semibold text-slate-800">
                    {demoFrameIndex === null ? '--' : demoFrameIndex + 1}
                    {demoFrameCount ? ` / ${demoFrameCount}` : ''}
                  </p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-[#ceead6] bg-white px-3 py-1 text-xs font-medium text-[#137333]">
                  {demoFrameKind === 'empty' ? '遮挡/无输入帧' : '测试集图片帧'}
                </span>
                {demoCachedDetection && (
                  <span className="rounded-full border border-[#d2e3fc] bg-white px-3 py-1 text-xs font-medium text-[#1a73e8]">
                    复用检测结果
                  </span>
                )}
                <span className="rounded-full border border-[#fbbc04]/40 bg-white px-3 py-1 text-xs font-medium text-[#b06000]">
                  库存同步默认开启
                </span>
              </div>
            </div>
          )}

          <div className="space-y-4 rounded-2xl border border-[#dadce0] bg-[#f8f9fa] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="flex items-center gap-2 font-medium text-slate-800">
                  <Icon name="database" size={18} className="text-[#1a73e8]" filled />
                  同步库存
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-500">
                  开启后将识别结果写入后端库存。
                  <br />
                  默认值来自系统设置页中的演示摄像头配置。
                </p>
              </div>
              <label className="relative mt-1 inline-flex cursor-pointer items-center">
                <input
                  type="checkbox"
                  className="peer sr-only"
                  checked={syncInventory}
                  onChange={(event) => setSyncInventory(event.target.checked)}
                />
                <div className="h-6 w-11 rounded-full bg-slate-300 shadow-sm after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-all after:content-[''] peer-checked:bg-[#1a73e8] peer-checked:after:translate-x-full" />
              </label>
            </div>

            {syncResult?.message && (
              <div className="rounded-xl border border-[#fbbc04]/30 bg-[#fef7e0] p-3 text-sm text-[#b06000]">
                {syncResult.message}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-2xl border border-[#dadce0] p-5 transition-shadow hover:shadow-sm">
              <p className="mb-1 text-xs font-semibold text-slate-500">检测框数量</p>
              <p className="text-3xl font-bold text-[#1a73e8]">{boxes.length}</p>
            </div>
            <div className="rounded-2xl border border-[#dadce0] p-5 transition-shadow hover:shadow-sm">
              <p className="mb-1 text-xs font-semibold text-slate-500">估计商品数量</p>
              <p className="text-3xl font-bold text-[#34a853]">{totalPredictedCount}</p>
            </div>
            <div className="rounded-2xl border border-[#dadce0] p-5 transition-shadow hover:shadow-sm">
              <p className="mb-1 text-xs font-semibold text-slate-500">最近回传</p>
              <p className="text-lg font-bold tracking-tight text-slate-800">
                {lastDetectionAt || '--:--:--'}
              </p>
            </div>
          </div>

          <div className="space-y-4 rounded-2xl border border-[#dadce0] p-5">
            <div className="flex items-center gap-2 font-bold text-slate-800">
              <Icon name="info" size={18} className="text-[#1a73e8]" filled />
              本次同步摘要
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="rounded-xl border border-slate-100 bg-[#f8f9fa] p-3">
                <p className="text-xs text-slate-500">更新商品数</p>
                <p className="mt-1 text-xl font-bold text-slate-800">
                  {syncResult?.updated_items ?? 0}
                </p>
              </div>
              <div className="rounded-xl border border-slate-100 bg-[#f8f9fa] p-3">
                <p className="text-xs text-slate-500">状态变化数</p>
                <p className="mt-1 text-xl font-bold text-slate-800">
                  {syncResult?.status_changes ?? 0}
                </p>
              </div>
            </div>

            <div className="rounded-xl border border-slate-100 bg-[#f8f9fa] p-3">
              <p className="text-xs text-slate-500">待确认状态数</p>
              <p className="mt-1 text-xl font-bold text-slate-800">
                {syncResult?.pending_status_count ?? 0}
              </p>
            </div>

            <div>
              <p className="mb-2 text-xs font-medium text-slate-500">商品维度估计数量</p>
              <div className="space-y-2">
                {syncedItemCounts.length ? (
                  syncedItemCounts.map(([itemName, count]) => (
                    <div
                      key={itemName}
                      className="rounded-xl border border-slate-100 bg-[#f8f9fa] px-3 py-2 text-sm text-slate-700"
                    >
                      {itemName}：{count} 件
                    </div>
                  ))
                ) : (
                  <span className="text-sm text-slate-400">暂无</span>
                )}
              </div>
            </div>

            <div>
              <p className="mb-2 text-xs font-medium text-slate-500">命中的库存标签</p>
              <div className="flex flex-wrap gap-2">
                {syncResult?.matched_labels?.length ? (
                  syncResult.matched_labels.map((label) => (
                    <span
                      key={label}
                      className="rounded-full border border-[#d2e3fc] bg-[#e8f0fe] px-3 py-1 text-xs font-medium text-[#1a73e8]"
                    >
                      {label}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-slate-400">暂无</span>
                )}
              </div>
            </div>

            {syncResult?.pending_updates?.length ? (
              <div>
                <p className="mb-2 text-xs font-medium text-slate-500">待确认状态</p>
                <div className="space-y-2">
                  {syncResult.pending_updates.map((item) => (
                    <div
                      key={item.item_id}
                      className="rounded-xl border border-[#dadce0] bg-white px-3 py-2 text-sm text-slate-600"
                    >
                      {item.item_name}：{item.status}（{item.frames_seen}/{item.frames_required}）
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>

          <div className="mt-auto space-y-1 px-1 text-xs text-slate-400">
            <p>
              WS 地址：<span className="break-all font-mono text-slate-500">{cameraWsUrl}</span>
            </p>
            <p>
              稳定模式：上一帧返回后再发送下一帧，间隔约 {DETECTION_INTERVAL_MS / 1000} 秒
            </p>
            {isDemoMode && (
              <p>
                数据集演示：重复 5-10 帧后自动插入遮挡空帧，摄像头 ID 为 {DEMO_CAMERA_ID}
              </p>
            )}
          </div>
        </motion.div>
      </div>
    </motion.div>
  );
}
