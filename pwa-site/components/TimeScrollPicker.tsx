'use client';
import { useLayoutEffect, useRef, useState } from 'react';
import { ChevronDown, Clock } from 'lucide-react';

interface TimeScrollPickerProps {
  label: string;
  value: string;
  defaultValue: string;
  onChange: (time: string) => void;
  disabled?: boolean;
}

const hours = Array.from({ length: 24 }, (_, index) => index);
const minutes = Array.from({ length: 60 }, (_, index) => index);

export default function TimeScrollPicker({ label, value, defaultValue, onChange, disabled = false }: TimeScrollPickerProps) {
  const [open, setOpen] = useState(false);
  const displayedValue = value || defaultValue;
  const [hourPart, minutePart] = displayedValue.split(':').map(Number);
  const [defaultHour, defaultMinute] = defaultValue.split(':').map(Number);
  const selectedHour = Number.isInteger(hourPart) && hourPart >= 0 && hourPart < 24 ? hourPart : defaultHour;
  const selectedMinute = Number.isInteger(minutePart) && minutePart >= 0 && minutePart < 60 ? minutePart : defaultMinute;
  const hoursRef = useRef<HTMLDivElement | null>(null);
  const minutesRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (!open) return;
    const center = (container: HTMLDivElement | null, selector: string) => {
      const item = container?.querySelector(selector) as HTMLElement | null;
      if (!container || !item) return;
      // Let the browser account for the actual scroll container/offset parent.
      // Manual offsetTop arithmetic can resolve to the end of the list on mobile.
      item.scrollIntoView({ block: 'center', inline: 'nearest' });
    };
    const frame = requestAnimationFrame(() => {
      center(hoursRef.current, `[data-hour="${selectedHour}"]`);
      center(minutesRef.current, `[data-minute="${selectedMinute}"]`);
    });
    return () => cancelAnimationFrame(frame);
  }, [open, selectedHour, selectedMinute]);

  const select = (hour: number, minute: number) => {
    onChange(`${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`);
  };
  const scrollerStyle = { height: '132px', overflowY: 'auto' as const, border: '1px solid var(--border)', borderRadius: '9px', background: '#fff', WebkitOverflowScrolling: 'touch' as const };
  const listStyle = { paddingBlock: '45px' };

  return <div>
    <label style={{ display: 'block', fontSize: '.72rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '.4px', marginBottom: 6 }}>{label}</label>
    <button type="button" disabled={disabled} aria-expanded={open} onClick={() => setOpen(current => !current)} style={{ width: '100%', minHeight: 44, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '10px 12px', background: '#fff', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)', fontSize: '1rem', fontWeight: 700, fontFamily: 'inherit' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Clock size={16} />{displayedValue}</span>
      <ChevronDown size={16} style={{ transform: open ? 'rotate(180deg)' : undefined, transition: 'transform .15s' }} />
    </button>
    {open && <div style={{ marginTop: 8, padding: 10, border: '1px solid var(--border)', borderRadius: 12, background: 'rgba(86,124,141,.05)', boxShadow: '0 8px 24px rgba(15,23,42,.10)' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', alignItems: 'center', gap: 8 }}>
        <div ref={hoursRef} style={scrollerStyle} aria-label="Heures"><div style={listStyle}>{hours.map(hour => <button key={hour} type="button" data-hour={hour} aria-pressed={selectedHour === hour} onClick={() => select(hour, selectedMinute)} style={{ width: '100%', minHeight: 42, border: 0, background: selectedHour === hour ? 'rgba(86,124,141,.16)' : 'transparent', color: selectedHour === hour ? 'var(--teal)' : 'var(--text-muted)', fontWeight: selectedHour === hour ? 800 : 500, fontSize: '1rem' }}>{String(hour).padStart(2, '0')}</button>)}</div></div>
        <strong style={{ fontSize: '1.3rem' }}>:</strong>
        <div ref={minutesRef} style={scrollerStyle} aria-label="Minutes"><div style={listStyle}>{minutes.map(minute => <button key={minute} type="button" data-minute={minute} aria-pressed={selectedMinute === minute} onClick={() => select(selectedHour, minute)} style={{ width: '100%', minHeight: 42, border: 0, background: selectedMinute === minute ? 'rgba(86,124,141,.16)' : 'transparent', color: selectedMinute === minute ? 'var(--teal)' : 'var(--text-muted)', fontWeight: selectedMinute === minute ? 800 : 500, fontSize: '1rem' }}>{String(minute).padStart(2, '0')}</button>)}</div></div>
      </div>
    </div>}
  </div>;
}
