'use client';
import { ChevronDown, Clock } from 'lucide-react';
import { useState } from 'react';

interface TimePickerProps {
  label: string;
  value?: string; // in format "HH:MM"
  onChange: (timeString: string) => void;
  className?: string;
  placeholder?: string;
}

const HOURS = Array.from({ length: 11 }, (_, i) => 8 + i); // 08 to 18
const MINUTES = [0, 15, 30, 45];

export function TimePicker({ label, value, onChange, className = '', placeholder = '08:00' }: TimePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  
  // Parse value to extract hours and minutes
  const parseTime = (timeStr?: string): { hours: number; minutes: number } => {
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
    <div className={className}>
      <label className="block text-sm text-savia-text-muted mb-1 flex items-center gap-1">
        <Clock className="w-3.5 h-3.5" /> {label}
      </label>
      <div className="relative">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="w-full bg-savia-surface-hover border border-savia-border rounded-lg px-4 py-2.5 text-savia-text placeholder:text-savia-text-dim focus:ring-2 focus:ring-savia-accent/40 outline-none transition-all text-left flex items-center justify-between"
        >
          <span className={selectedHours === 8 && selectedMinutes === 0 ? 'text-savia-text-dim' : 'text-savia-text'}>
            {displayValue}
          </span>
          <ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
        </button>

        {isOpen && (
          <div className="absolute top-full left-0 right-0 mt-2 bg-savia-surface border border-savia-border rounded-lg shadow-xl z-50 p-3">
            <div className="grid grid-cols-2 gap-2">
              {/* Hours */}
              <div>
                <div className="text-xs font-bold text-savia-text-muted mb-2 uppercase tracking-wide">Heures</div>
                <div className="space-y-1 max-h-48 overflow-y-auto">
                  {HOURS.map((h) => (
                    <button
                      key={h}
                      type="button"
                      onClick={() => handleHourSelect(h)}
                      className={`w-full py-2 rounded text-sm font-semibold transition-colors cursor-pointer ${
                        selectedHours === h
                          ? 'bg-savia-accent text-white'
                          : 'bg-savia-surface-hover text-savia-text hover:bg-savia-accent/30'
                      }`}
                    >
                      {String(h).padStart(2, '0')}
                    </button>
                  ))}
                </div>
              </div>

              {/* Minutes */}
              <div>
                <div className="text-xs font-bold text-savia-text-muted mb-2 uppercase tracking-wide">Minutes</div>
                <div className="space-y-1">
                  {MINUTES.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => handleMinuteSelect(m)}
                      className={`w-full py-2 rounded text-sm font-semibold transition-colors cursor-pointer ${
                        selectedMinutes === m
                          ? 'bg-savia-accent text-white'
                          : 'bg-savia-surface-hover text-savia-text hover:bg-savia-accent/30'
                      }`}
                    >
                      {String(m).padStart(2, '0')}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
