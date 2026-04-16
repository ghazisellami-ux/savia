'use client';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isLoggedIn } from '@/lib/auth';

export default function RootPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(isLoggedIn() ? '/interventions' : '/login');
  }, [router]);
  return (
    <div className="flex items-center justify-center min-h-screen" style={{ background: 'var(--beige)' }}>
      <div className="w-8 h-8 rounded-full border-4 animate-spin" style={{ borderColor: 'var(--sky)', borderTopColor: 'var(--teal)' }} />
    </div>
  );
}
