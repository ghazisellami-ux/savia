/**
 * Download a Blob as a file. Uses multiple strategies for maximum
 * browser compatibility (some browsers block programmatic <a>.click()
 * when triggered from an async context).
 */
export function downloadBlob(blob: Blob, filename: string): void {
  // Strategy 1: Use navigator.msSaveBlob for old Edge/IE (unlikely but safe)
  if (typeof (navigator as any).msSaveBlob === 'function') {
    (navigator as any).msSaveBlob(blob, filename);
    return;
  }

  const url = URL.createObjectURL(blob);

  // Strategy 2: Create an <a> element and dispatch a MouseEvent
  // (more reliable than .click() in async contexts)
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.position = 'fixed';
  link.style.left = '-9999px';
  link.style.top = '-9999px';
  document.body.appendChild(link);

  // Use dispatchEvent instead of .click() — works better in async flows
  const evt = new MouseEvent('click', {
    bubbles: true,
    cancelable: true,
    view: window,
  });
  link.dispatchEvent(evt);

  // Cleanup after generous delay
  setTimeout(() => {
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, 10000);
}
