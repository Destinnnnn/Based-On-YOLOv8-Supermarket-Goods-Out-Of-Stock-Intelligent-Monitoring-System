import React from 'react';
import clsx from 'clsx';

interface IconProps extends React.HTMLAttributes<HTMLSpanElement> {
  name: string;
  filled?: boolean;
  size?: number;
}

type SvgProps = {
  filled: boolean;
};

const strokeProps = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

const icons: Record<string, (props: SvgProps) => React.ReactNode> = {
  add: () => (
    <>
      <path d="M12 5v14" {...strokeProps} />
      <path d="M5 12h14" {...strokeProps} />
    </>
  ),
  arrow_forward: () => <path d="M5 12h14m-6-6 6 6-6 6" {...strokeProps} />,
  arrow_downward: () => (
    <>
      <path d="M12 4v16" {...strokeProps} />
      <path d="m6 14 6 6 6-6" {...strokeProps} />
    </>
  ),
  arrow_upward: () => (
    <>
      <path d="M12 20V4" {...strokeProps} />
      <path d="m6 10 6-6 6 6" {...strokeProps} />
    </>
  ),
  bar_chart: () => (
    <>
      <path d="M4 19V5" {...strokeProps} />
      <path d="M4 19h16" {...strokeProps} />
      <path d="M8 16V9" {...strokeProps} />
      <path d="M12 16V6" {...strokeProps} />
      <path d="M16 16v-4" {...strokeProps} />
    </>
  ),
  cable: () => (
    <>
      <path d="M7 7l10 10" {...strokeProps} />
      <path d="M8 2l4 4-6 6-4-4 6-6z" {...strokeProps} />
      <path d="M16 22l-4-4 6-6 4 4-6 6z" {...strokeProps} />
    </>
  ),
  calendar_today: () => (
    <>
      <rect x="4" y="5" width="16" height="15" rx="2" {...strokeProps} />
      <path d="M8 3v4M16 3v4M4 10h16" {...strokeProps} />
    </>
  ),
  camera: () => (
    <>
      <path d="M4 8a2 2 0 0 1 2-2h2l2-2h4l2 2h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8z" {...strokeProps} />
      <circle cx="12" cy="13" r="4" {...strokeProps} />
    </>
  ),
  check_circle: ({ filled }) => (
    <>
      <circle cx="12" cy="12" r="9" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" />
      <path d="m8 12 2.5 2.5L16 9" fill="none" stroke={filled ? 'white' : 'currentColor'} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  close: () => (
    <>
      <path d="M6 6l12 12" {...strokeProps} />
      <path d="M18 6 6 18" {...strokeProps} />
    </>
  ),
  dashboard: () => (
    <>
      <rect x="4" y="4" width="7" height="7" rx="1.5" {...strokeProps} />
      <rect x="13" y="4" width="7" height="7" rx="1.5" {...strokeProps} />
      <rect x="4" y="13" width="7" height="7" rx="1.5" {...strokeProps} />
      <rect x="13" y="13" width="7" height="7" rx="1.5" {...strokeProps} />
    </>
  ),
  database: () => (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" {...strokeProps} />
      <path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6" {...strokeProps} />
      <path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" {...strokeProps} />
    </>
  ),
  delete: () => (
    <>
      <path d="M4 7h16" {...strokeProps} />
      <path d="M10 11v6M14 11v6" {...strokeProps} />
      <path d="M6 7l1 14h10l1-14M9 7V4h6v3" {...strokeProps} />
    </>
  ),
  description: () => (
    <>
      <path d="M6 3h9l3 3v15H6V3z" {...strokeProps} />
      <path d="M14 3v4h4M9 12h6M9 16h6" {...strokeProps} />
    </>
  ),
  download: () => (
    <>
      <path d="M12 4v11" {...strokeProps} />
      <path d="m7 10 5 5 5-5" {...strokeProps} />
      <path d="M5 20h14" {...strokeProps} />
    </>
  ),
  edit: () => (
    <>
      <path d="M4 20h4l10.5-10.5-4-4L4 16v4z" {...strokeProps} />
      <path d="m13.5 6.5 4 4" {...strokeProps} />
    </>
  ),
  error: ({ filled }) => (
    <>
      <circle cx="12" cy="12" r="9" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" />
      <path d="M12 7v6" stroke={filled ? 'white' : 'currentColor'} strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="17" r="1" fill={filled ? 'white' : 'currentColor'} />
    </>
  ),
  filter_list: () => (
    <>
      <path d="M4 6h16" {...strokeProps} />
      <path d="M7 12h10" {...strokeProps} />
      <path d="M10 18h4" {...strokeProps} />
    </>
  ),
  fullscreen: () => (
    <>
      <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" {...strokeProps} />
    </>
  ),
  hourglass_top: () => (
    <>
      <path d="M7 3h10M7 21h10M8 3c0 5 8 5 8 10s-8 5-8 8M16 3c0 3-2 4-4 5" {...strokeProps} />
    </>
  ),
  info: ({ filled }) => (
    <>
      <circle cx="12" cy="12" r="9" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" />
      <path d="M12 11v6" stroke={filled ? 'white' : 'currentColor'} strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="7.5" r="1" fill={filled ? 'white' : 'currentColor'} />
    </>
  ),
  inventory_2: () => (
    <>
      <path d="M4 7 12 3l8 4-8 4-8-4z" {...strokeProps} />
      <path d="M4 7v10l8 4 8-4V7" {...strokeProps} />
      <path d="M12 11v10" {...strokeProps} />
    </>
  ),
  link: () => (
    <>
      <path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1" {...strokeProps} />
      <path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1" {...strokeProps} />
    </>
  ),
  lock: () => (
    <>
      <rect x="5" y="10" width="14" height="10" rx="2" {...strokeProps} />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" {...strokeProps} />
    </>
  ),
  logout: () => (
    <>
      <path d="M10 5H6v14h4" {...strokeProps} />
      <path d="M14 8l4 4-4 4" {...strokeProps} />
      <path d="M18 12H9" {...strokeProps} />
    </>
  ),
  menu: () => (
    <>
      <path d="M4 6h16M4 12h16M4 18h16" {...strokeProps} />
    </>
  ),
  notifications: () => (
    <>
      <path d="M6 17h12l-1.5-2V10a4.5 4.5 0 0 0-9 0v5L6 17z" {...strokeProps} />
      <path d="M10 19a2 2 0 0 0 4 0" {...strokeProps} />
    </>
  ),
  person: () => (
    <>
      <circle cx="12" cy="8" r="4" {...strokeProps} />
      <path d="M5 21a7 7 0 0 1 14 0" {...strokeProps} />
    </>
  ),
  save: () => (
    <>
      <path d="M5 4h12l2 2v14H5V4z" {...strokeProps} />
      <path d="M8 4v6h8V4M8 20v-6h8v6" {...strokeProps} />
    </>
  ),
  search: () => (
    <>
      <circle cx="11" cy="11" r="6" {...strokeProps} />
      <path d="m16 16 4 4" {...strokeProps} />
    </>
  ),
  settings: () => (
    <>
      <circle cx="12" cy="12" r="3" {...strokeProps} />
      <path d="M19 12a7.1 7.1 0 0 0-.1-1l2-1.5-2-3.4-2.4 1a8 8 0 0 0-1.8-1L14.4 3h-4.8l-.3 3.1a8 8 0 0 0-1.8 1l-2.4-1-2 3.4 2 1.5a7.1 7.1 0 0 0 0 2l-2 1.5 2 3.4 2.4-1a8 8 0 0 0 1.8 1l.3 3.1h4.8l.3-3.1a8 8 0 0 0 1.8-1l2.4 1 2-3.4-2-1.5c.1-.3.1-.7.1-1z" {...strokeProps} />
    </>
  ),
  smart_display: () => (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" {...strokeProps} />
      <path d="m10 9 5 3-5 3V9z" fill="currentColor" />
    </>
  ),
  stop: () => <rect x="7" y="7" width="10" height="10" rx="1" fill="currentColor" />,
  sync: () => (
    <>
      <path d="M20 6v5h-5" {...strokeProps} />
      <path d="M4 18v-5h5" {...strokeProps} />
      <path d="M18 10a6 6 0 0 0-10-4L4 10M6 14a6 6 0 0 0 10 4l4-4" {...strokeProps} />
    </>
  ),
  table_view: () => (
    <>
      <rect x="4" y="5" width="16" height="14" rx="1" {...strokeProps} />
      <path d="M4 10h16M10 5v14" {...strokeProps} />
    </>
  ),
  trending_down: () => (
    <>
      <path d="M4 7l6 6 4-4 6 6" {...strokeProps} />
      <path d="M15 15h5v-5" {...strokeProps} />
    </>
  ),
  trending_up: () => (
    <>
      <path d="M4 17l6-6 4 4 6-6" {...strokeProps} />
      <path d="M15 9h5v5" {...strokeProps} />
    </>
  ),
  unfold_more: () => (
    <>
      <path d="m8 8 4-4 4 4" {...strokeProps} />
      <path d="m8 16 4 4 4-4" {...strokeProps} />
    </>
  ),
  upload: () => (
    <>
      <path d="M12 20V9" {...strokeProps} />
      <path d="m7 14 5-5 5 5" {...strokeProps} />
      <path d="M5 4h14" {...strokeProps} />
    </>
  ),
  videocam: () => (
    <>
      <rect x="3" y="7" width="12" height="10" rx="2" {...strokeProps} />
      <path d="m15 11 5-3v8l-5-3v-2z" {...strokeProps} />
    </>
  ),
  videocam_off: () => (
    <>
      <path d="M3 3l18 18" {...strokeProps} />
      <path d="M8 7h7v7M15 11l5-3v8l-3-2" {...strokeProps} />
      <path d="M5 7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h8" {...strokeProps} />
    </>
  ),
  warning: ({ filled }) => (
    <>
      <path d="M12 3 2.5 20h19L12 3z" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M12 9v5" stroke={filled ? 'white' : 'currentColor'} strokeWidth="2" strokeLinecap="round" />
      <circle cx="12" cy="17" r="1" fill={filled ? 'white' : 'currentColor'} />
    </>
  ),
  wifi: () => (
    <>
      <path d="M4 9a12 12 0 0 1 16 0" {...strokeProps} />
      <path d="M7 12.5a7.5 7.5 0 0 1 10 0" {...strokeProps} />
      <path d="M10 16a3 3 0 0 1 4 0" {...strokeProps} />
      <circle cx="12" cy="19" r="1" fill="currentColor" />
    </>
  ),
  wifi_off: () => (
    <>
      <path d="M3 3l18 18" {...strokeProps} />
      <path d="M4 9a12 12 0 0 1 10.5-2.8M7 12.5a7.5 7.5 0 0 1 8-.5M10 16a3 3 0 0 1 4 0" {...strokeProps} />
      <circle cx="12" cy="19" r="1" fill="currentColor" />
    </>
  ),
};

export const Icon: React.FC<IconProps> = ({
  name,
  filled = false,
  size = 24,
  className,
  ...props
}) => {
  const renderIcon = icons[name] ?? icons.info;

  return (
    <span
      className={clsx('inline-flex items-center justify-center align-middle leading-none', className)}
      style={{ width: size, height: size, ...props.style }}
      aria-hidden="true"
      {...props}
    >
      <svg
        viewBox="0 0 24 24"
        width={size}
        height={size}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {renderIcon({ filled })}
      </svg>
    </span>
  );
};
