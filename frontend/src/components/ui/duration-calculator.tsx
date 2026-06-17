'use client';
import { Clock, Zap } from 'lucide-react';
import { useEffect, useState } from 'react';
import { TimePicker } from './time-picker';

interface DurationCalculatorProps {
  startTime?: string; // HH:MM format
  endTime?: string;   // HH:MM format
  onDurationChange: (durationHours: number) => void;
  label?: string;
  helpText?: string;
}

export function DurationCalculator({
  startTime = '08:00',
  endTime = '09:00',
  onDurationChange,
  label = 'Durée d\'intervention',
  helpText = 'Minimum 1 heure de facturation',
}: DurationCalculatorProps) {
  const [start, setStart] = useState(startTime);
  const [end, setEnd] = useState(endTime);
  const [calculatedDuration, setCalculatedDuration] = useState<number>(1);

  // Calculate duration whenever times change
  useEffect(() => {
    const [startH, startM] = start.split(':').map(Number);
    const [endH, endM] = end.split(':').map(Number);

    const startMinutes = startH * 60 + startM;
    const endMinutes = endH * 60 + endM;

    let durationMinutes = endMinutes - startMinutes;

    // Handle case where end time is next day (crossing midnight)
    if (durationMinutes <= 0) {
      durationMinutes += 24 * 60;
    }

    // Convert to hours
    let durationHours = durationMinutes / 60;

    // Enforce minimum 1 hour billing
    durationHours = Math.max(1, durationHours);

    // Round to 2 decimal places
    durationHours = Math.round(durationHours * 100) / 100;

    setCalculatedDuration(durationHours);
    onDurationChange(durationHours);
  }, [start, end, onDurationChange]);

  return (
    <div className="space-y-3 p-4 bg-savia-surface-hover/50 rounded-lg border border-savia-border/30">
      <div className="flex items-center gap-2 mb-2">
        <Clock className="w-4 h-4 text-savia-accent" />
        <h3 className="text-sm font-bold text-savia-text uppercase tracking-wide">{label}</h3>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <TimePicker
          label="Heure de début"
          value={start}
          onChange={setStart}
        />
        <TimePicker
          label="Heure de fin"
          value={end}
          onChange={setEnd}
        />
      </div>

      {/* Duration Display */}
      <div className="flex items-center gap-2 pt-2 px-3 py-2 rounded-lg bg-savia-accent/10 border border-savia-accent/20">
        <Zap className="w-4 h-4 text-savia-accent" />
        <span className="text-xs text-savia-text-muted">Durée calculée:</span>
        <span className="font-bold text-savia-accent">{calculatedDuration}h</span>
        <span className="text-xs text-savia-text-muted ml-auto">{helpText}</span>
      </div>
    </div>
  );
}
