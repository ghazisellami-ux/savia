'use client';
import { useState, useRef, useEffect } from 'react';

interface TimeScrollPickerProps {
  label: string;
  value: string; // HH:MM format
  onChange: (time: string) => void;
}

export default function TimeScrollPicker({ label, value, onChange }: TimeScrollPickerProps) {
  const [selectedHour, setSelectedHour] = useState<number>(
    value ? parseInt(value.split(':')[0]) : 12
  );
  const [selectedMinute, setSelectedMinute] = useState<number>(
    value ? parseInt(value.split(':')[1]) : 0
  );

  const hoursRef = useRef<HTMLDivElement | null>(null);
  const minutesRef = useRef<HTMLDivElement | null>(null);

  const hours = Array.from({ length: 24 }, (_, i) => i);
  const minutes = [0, 15, 30, 45];

  useEffect(() => {
    const newTime = `${String(selectedHour).padStart(2, '0')}:${String(selectedMinute).padStart(2, '0')}`;
    onChange(newTime);
  }, [selectedHour, selectedMinute, onChange]);

  useEffect(() => {
    // Auto-scroll to selected hour on mount or value change
    if (hoursRef.current) {
      const item = hoursRef.current.querySelector(`[data-hour="${selectedHour}"]`);
      if (item) {
        const element = item as HTMLElement;
        hoursRef.current.scrollTo({
          top: Math.max(0, element.offsetTop - (hoursRef.current.clientHeight - element.offsetHeight) / 2),
          behavior: 'auto',
        });
      }
    }
  }, [selectedHour]);

  useEffect(() => {
    // Auto-scroll to selected minute on mount or value change
    if (minutesRef.current) {
      const item = minutesRef.current.querySelector(`[data-minute="${selectedMinute}"]`);
      if (item) {
        const element = item as HTMLElement;
        minutesRef.current.scrollTo({
          top: Math.max(0, element.offsetTop - (minutesRef.current.clientHeight - element.offsetHeight) / 2),
          behavior: 'auto',
        });
      }
    }
  }, [selectedMinute]);

  return (
    <div style={{ marginBottom: '16px' }}>
      <label style={{
        display: 'block',
        fontSize: '0.75rem',
        fontWeight: 700,
        color: 'var(--text-muted)',
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '8px',
      }}>
        {label}
      </label>

      <div style={{
        display: 'flex',
        gap: '8px',
        alignItems: 'center',
        background: '#fff',
        border: '1px solid var(--border)',
        borderRadius: '10px',
        padding: '12px',
      }}>
        {/* Hours Scroller (LEFT) */}
        <div style={{ flex: 1 }}>
          <div
            ref={hoursRef}
            style={{
              height: '140px',
              overflowY: 'scroll',
              overflowX: 'hidden',
              textAlign: 'center',
              scrollBehavior: 'smooth',
              WebkitOverflowScrolling: 'touch',
              display: 'flex',
              flexDirection: 'column',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              background: 'rgba(86,124,141,0.02)',
              padding: '8px 0',
            }}
          >
            {hours.map((h) => (
              <div
                key={h}
                data-hour={h}
                onClick={() => setSelectedHour(h)}
                style={{
                  padding: '14px 8px',
                  fontSize: '1rem',
                  fontWeight: selectedHour === h ? 700 : 500,
                  color: selectedHour === h ? 'var(--teal)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  background: selectedHour === h ? 'rgba(86, 124, 141, 0.15)' : 'transparent',
                  borderRadius: '4px',
                  margin: '2px 4px',
                  minHeight: '40px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  userSelect: 'none',
                }}
              >
                {String(h).padStart(2, '0')}
              </div>
            ))}
          </div>
        </div>

        {/* Separator */}
        <div style={{
          fontSize: '1.5rem',
          fontWeight: 700,
          color: 'var(--text)',
          paddingTop: '4px',
        }}>
          :
        </div>

        {/* Minutes Scroller (RIGHT) */}
        <div style={{ flex: 1 }}>
          <div
            ref={minutesRef}
            style={{
              height: '140px',
              overflowY: 'scroll',
              overflowX: 'hidden',
              textAlign: 'center',
              scrollBehavior: 'smooth',
              WebkitOverflowScrolling: 'touch',
              display: 'flex',
              flexDirection: 'column',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              background: 'rgba(86,124,141,0.02)',
              padding: '8px 0',
            }}
          >
            {minutes.map((m) => (
              <div
                key={m}
                data-minute={m}
                onClick={() => setSelectedMinute(m)}
                style={{
                  padding: '14px 8px',
                  fontSize: '1rem',
                  fontWeight: selectedMinute === m ? 700 : 500,
                  color: selectedMinute === m ? 'var(--teal)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  background: selectedMinute === m ? 'rgba(86, 124, 141, 0.15)' : 'transparent',
                  borderRadius: '4px',
                  margin: '2px 4px',
                  minHeight: '40px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  userSelect: 'none',
                }}
              >
                {String(m).padStart(2, '0')}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
