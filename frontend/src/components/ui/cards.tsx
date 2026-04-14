'use client';
// ==========================================
// 📊 KPI Card — Composant réutilisable
// ==========================================
import { clsx } from 'clsx';

interface KpiCardProps {
  icon: React.ReactNode;
  value: string;
  label: string;
  variant?: 'default' | 'danger' | 'success' | 'warning';
  tooltip?: string;
}

export function KpiCard({ icon, value, label, variant = 'default', tooltip }: KpiCardProps) {
  const borderColor = {
    default: 'border-savia-accent/20',
    danger: 'border-savia-danger/30',
    success: 'border-savia-success/30',
    warning: 'border-savia-warning/30',
  }[variant];

  const glowColor = {
    default: 'hover:shadow-[0_0_20px_rgba(45,212,191,0.1)]',
    danger: 'hover:shadow-[0_0_20px_rgba(239,68,68,0.1)]',
    success: 'hover:shadow-[0_0_20px_rgba(34,197,94,0.1)]',
    warning: 'hover:shadow-[0_0_20px_rgba(245,158,11,0.1)]',
  }[variant];

  return (
    <div
      className={clsx(
        'glass rounded-xl p-4 text-center transition-all duration-300',
        borderColor, glowColor,
        'hover:scale-[1.02] hover:-translate-y-0.5'
      )}
      title={tooltip}
    >
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-xl font-extrabold text-savia-text tracking-tight">{value}</div>
      <div className="text-xs text-savia-text-muted mt-1 leading-tight">{label}</div>
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
