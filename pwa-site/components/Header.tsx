'use client';
import { useRouter, usePathname } from 'next/navigation';
import Image from 'next/image';
import { getUser, clearSession } from '@/lib/auth';
import { useState, useEffect } from 'react';
import { LogOut } from 'lucide-react';

interface HeaderProps {
  syncCount?: number;
  notifCount?: number;
}

export default function Header({ syncCount = 0, notifCount = 0 }: HeaderProps) {
  const router = useRouter();
  const user = getUser();

  const handleLogout = () => {
    clearSession();
    router.replace('/login');
  };

  return (
    <header style={{
      position: 'fixed', top: 0, left: 0, right: 0, height: 'var(--header-h)',
      background: 'var(--navy)', borderBottom: '1px solid rgba(255,255,255,0.1)',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 16px', zIndex: 900,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <Image src="/logo-savia.png" alt="SAVIA" width={80} height={50} unoptimized className="object-contain" style={{ filter: 'brightness(0) invert(1)' }} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        {syncCount > 0 && (
          <span className="animate-pulse-dot" style={{ background: 'var(--warning)', color: '#000', fontSize: '0.65rem', fontWeight: 800, minWidth: '22px', height: '22px', borderRadius: '11px', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '0 6px' }}>
            {syncCount}
          </span>
        )}
        <span style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', fontWeight: 600 }}>{user?.nom}</span>
        <button onClick={handleLogout} style={{ background: 'rgba(255,255,255,0.1)', border: 'none', color: '#fff', padding: '6px 10px', borderRadius: '8px', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
          <LogOut style={{ width: 16, height: 16 }} />
        </button>
      </div>
    </header>
  );
}
