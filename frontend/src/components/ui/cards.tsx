'use client';
// ==========================================
// 📊 KPI Card — Composant réutilisable
// ==========================================
import { clsx } from 'clsx';

interface KpiCardProps {
  icon?: React.ReactNode;
  value?: string;
  label?: string;
  variant?: 'default' | 'danger' | 'success' | 'warning' | 'skeleton';
  tooltip?: string;
  detail?: string;
  loading?: boolean;
  appearance?: 'default' | 'status-stripe';
  emphasis?: boolean;
  className?: string;
  onClick?: () => void;
}

export function KpiCard({ icon, value, label, variant = 'default', tooltip, detail, loading = false, appearance = 'default', emphasis = false, className, onClick }: KpiCardProps) {
  // Skeleton variant - shows grayed out placeholder
  if (variant === 'skeleton') {
    return (
      <div
        className={clsx(
          'glass rounded-xl text-center transition-all duration-300',
          emphasis ? 'flex min-h-40 flex-col items-center justify-center p-5' : 'p-4',
          'border-savia-border/20 opacity-50',
          'animate-pulse'
        )}
      >
        <div className={emphasis ? 'mb-2 text-3xl text-savia-text-dim' : 'mb-1 text-2xl text-savia-text-dim'}>⚙️</div>
        <div className={emphasis ? 'text-2xl font-extrabold tracking-tight text-savia-text-dim md:text-3xl' : 'text-xl font-extrabold text-savia-text-dim tracking-tight'}>0</div>
        <div className={emphasis ? 'mt-2 text-sm font-semibold leading-tight text-savia-text-dim' : 'text-xs text-savia-text-dim mt-1 leading-tight'}>Chargement...</div>
      </div>
    );
  }

  const borderColor = {
    default: 'border-savia-accent/20',
    danger: 'border-red-500/20 bg-red-500/10',
    success: 'border-green-500/20 bg-green-500/10',
    warning: 'border-amber-500/20 bg-amber-500/10',
  }[variant];

  const glowColor = {
    default: 'hover:shadow-[0_0_20px_rgba(212,163,115,0.1)]',
    danger: 'hover:shadow-[0_0_20px_rgba(239,68,68,0.1)]',
    success: 'hover:shadow-[0_0_20px_rgba(34,197,94,0.1)]',
    warning: 'hover:shadow-[0_0_20px_rgba(245,158,11,0.1)]',
  }[variant];

  const stripeGradient = {
    default: 'linear-gradient(90deg, #567C8D 0%, rgba(86,124,141,0.16) 100%)',
    danger: 'linear-gradient(90deg, #EF4444 0%, rgba(239,68,68,0.16) 100%)',
    success: 'linear-gradient(90deg, #22C55E 0%, rgba(34,197,94,0.16) 100%)',
    warning: 'linear-gradient(90deg, #F59E0B 0%, rgba(245,158,11,0.16) 100%)',
  }[variant];

  const iconSurface = {
    default: 'rounded-full bg-savia-surface-hover p-2',
    danger: 'rounded-full bg-red-500/10 p-2',
    success: 'rounded-full bg-green-500/10 p-2',
    warning: 'rounded-full bg-amber-500/10 p-2',
  }[variant];

  const valueColor = loading ? 'text-savia-text' : {
    default: 'text-savia-text',
    danger: 'text-red-500',
    success: 'text-green-500',
    warning: 'text-amber-500',
  }[variant];

  return (
    <div
      className={clsx(
        'glass rounded-xl text-center transition-all duration-300',
        emphasis ? 'flex min-h-40 flex-col items-center justify-center p-5' : 'p-4',
        borderColor, glowColor,
        appearance === 'status-stripe' && 'relative overflow-hidden',
        'hover:scale-[1.02] hover:-translate-y-0.5',
        onClick && 'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-savia-accent',
        className
      )}
      title={tooltip}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onClick();
        }
      } : undefined}
    >
      {appearance === 'status-stripe' && <div aria-hidden="true" className="absolute left-0 right-0 top-0 z-10" style={{ height: '3px', background: stripeGradient }} />}
      <div className={clsx(emphasis ? 'mb-2 scale-110' : 'mb-1 text-2xl', loading && 'animate-pulse opacity-60', appearance === 'status-stripe' && iconSurface)}>{icon}</div>
      <div className={clsx(emphasis ? 'text-2xl font-extrabold tracking-tight md:text-3xl' : 'text-xl font-extrabold tracking-tight', valueColor, loading && 'animate-pulse')}>{loading ? '—' : value}</div>
      <div className={emphasis ? 'mt-2 text-sm font-semibold leading-tight text-savia-text-muted' : 'text-xs text-savia-text-muted mt-1 leading-tight'}>{label}</div>
      {detail && <div className="mt-2 text-xs leading-tight text-savia-text-muted">{loading ? 'Chargement…' : detail}</div>}
    </div>
  );
}

// ==========================================
// 🏥 Health Badge
// ==========================================
interface HealthBadgeProps {
  score: number;
  size?: 'sm' | 'md' | 'lg';
}

export function HealthBadge({ score, size = 'md' }: HealthBadgeProps) {
  const color = score >= 60 ? 'text-savia-success' : score >= 30 ? 'text-savia-warning' : 'text-savia-danger';
  const bg = score >= 60 ? 'bg-green-500/10' : score >= 30 ? 'bg-yellow-500/10' : 'bg-red-500/10';
  const dotColor = score >= 60 ? 'bg-green-400' : score >= 30 ? 'bg-yellow-400' : 'bg-red-400';
  const sizeClass = size === 'sm' ? 'text-xs px-2 py-0.5' : size === 'lg' ? 'text-base px-4 py-2' : 'text-sm px-3 py-1';

  return (
    <span className={clsx('inline-flex items-center gap-1 rounded-full font-bold', color, bg, sizeClass)}>
      <span className={clsx('w-2 h-2 rounded-full', dotColor)} /> {score}%
    </span>
  );
}

// ==========================================
// 📊 Section Card
// ==========================================
interface SectionCardProps {
  title: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function SectionCard({ title, children, className }: SectionCardProps) {
  return (
    <div className={clsx('glass rounded-xl p-5 animate-fade-in', className)}>
      <h3 className="text-sm font-bold text-savia-text-muted uppercase tracking-wider mb-4">{title}</h3>
      {children}
    </div>
  );
}
