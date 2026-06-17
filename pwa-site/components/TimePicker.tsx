'use client';
import { ChevronDown, Clock } from 'lucide-react';
import { useState } from 'react';

interface TimePickerProps {
  label: string;
  value?: string;
  onChange: (timeString: string) => void;
}

const HOURS = Array.from({ length: 11 }, (_, i) => 8 + i);
const MINUTES = [0, 15, 30, 45];

export default function TimePicker({ label, value, onChange }: TimePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  
  const parseTime = (timeStr?: string) => {
    if (!timeStr) return { hours: 8, minutes: 0 };
    const [h, m] = timeStr.split(':').map(Number);
    return { hours: h || 8, minutes: m || 0 };
  };
  
  const { hours: selectedHours, minutes: selectedMinutes } = parseTime(value);
  const displayValue = `${String(selectedHours).padStart(2, '0')}:${String(selectedMinutes).padStart(2, '0')}`;

  const handleHourSelect = (h: number) => {
    const newTime = `${String(h).padStart(2, '0')}:${String(selectedMinutes).padStart(2, '0')}`;
    onChange(newTime);
  };

  const handleMinuteSelect = (m: number) => {
    const newTime = `${String(selectedHours).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
    onChange(newTime);
    setIsOpen(false);
  };

  return (
    <div>
      <label style={{ display: 'flex', fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '6px', alignItems: 'center', gap: '4px' }}>
        <Clock style={{ width: 14, height: 14 }} /> {label}
      </label>
      <div style={{ position: 'relative' }}>
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          style={{
            width: '100%', background: '#fff', border: '1px solid var(--border)',
            borderRadius: '10px', color: 'var(--text)', padding: '12px 14px',
            fontSize: '1rem', outline: 'none', fontFamily: 'inherit',
            textAlign: 'left', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer'
          }}
        >
          <span>{displayValue}</span>
          <ChevronDown style={{ width: 16, height: 16 }} />
        </button>

        {isOpen && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '8px',
            background: '#fff', border: '1px solid var(--border)', borderRadius: '10px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)', zIndex: 50, padding: '12px',
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px'
          }}>
            <div>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase' }}>Heures</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '160px', overflowY: 'auto' }}>
                {HOURS.map((h) => (
                  <button
                    key={h}
                    type="button"
                    onClick={() => handleHourSelect(h)}
                    style={{
                      padding: '8px 10px', borderRadius: '8px', fontSize: '0.85rem', fontWeight: 600,
                      border: 'none', background: selectedHours === h ? 'var(--teal)' : '#f0f0f0',
                      color: selectedHours === h ? '#fff' : 'var(--text)', cursor: 'pointer'
                    }}
                  >
                    {String(h).padStart(2, '0')}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div style={{ fontSize: '0.65rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase' }}>Minutes</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {MINUTES.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => handleMinuteSelect(m)}
                    style={{
                      padding: '8px 10px', borderRadius: '8px', fontSize: '0.85rem', fontWeight: 600,
                      border: 'none', background: selectedMinutes === m ? 'var(--teal)' : '#f0f0f0',
                      color: selectedMinutes === m ? '#fff' : 'var(--text)', cursor: 'pointer'
                    }}
                  >
                    {String(m).padStart(2, '0')}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
