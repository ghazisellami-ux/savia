'use client';

import { useEffect, useRef, useState } from 'react';

import {
  applySelectedCurrency,
  ATTRS,
  type Lang,
  normalizeCurrencyCode,
  normalizeLang,
  SKIP_TAGS,
  translateText,
} from '@/lib/i18n-translation';

export default function I18nRuntime() {
  const [lang, setLang] = useState<Lang>(() => {
    if (typeof window === 'undefined') return 'fr';
    return normalizeLang(window.localStorage.getItem('savia_lang'));
  });
  const [currency, setCurrency] = useState(() => {
    if (typeof window === 'undefined') return 'TND';
    return normalizeCurrencyCode(window.localStorage.getItem('savia_devise'));
  });
  const originals = useRef<WeakMap<Text, string>>(new WeakMap());
  const renderedText = useRef<WeakMap<Text, string>>(new WeakMap());
  const renderedAttrs = useRef<WeakMap<Element, Map<string, string>>>(new WeakMap());
  const observer = useRef<MutationObserver | null>(null);

  useEffect(() => {
    const loadSettings = async () => {
      const token = localStorage.getItem('savia_token');
      if (!token) return;
      try {
        const res = await fetch('/api/settings/public', { headers: { Authorization: `Bearer ${token}` } });
        if (!res.ok) return;
        const data = await res.json();
        const next = normalizeLang(data.langue);
        localStorage.setItem('savia_lang', next);
        setLang(next);
        const nextCurrency = normalizeCurrencyCode(data.devise || localStorage.getItem('savia_devise'));
        localStorage.setItem('savia_devise', nextCurrency);
        setCurrency(nextCurrency);
      } catch {}
    };

    loadSettings();

    const onLanguage = (event: Event) => {
      const detailLang = (event as CustomEvent<{ lang?: string }>).detail?.lang;
      setLang(normalizeLang(detailLang || localStorage.getItem('savia_lang')));
    };
    const refreshCurrency = () => setCurrency(normalizeCurrencyCode(localStorage.getItem('savia_devise')));
    const onSettings = () => {
      setLang(normalizeLang(localStorage.getItem('savia_lang')));
      refreshCurrency();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === 'savia_lang') setLang(normalizeLang(event.newValue));
      if (event.key === 'savia_devise') setCurrency(normalizeCurrencyCode(event.newValue));
    };

    window.addEventListener('savia_language_changed', onLanguage);
    window.addEventListener('savia_settings_changed', onSettings);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('savia_language_changed', onLanguage);
      window.removeEventListener('savia_settings_changed', onSettings);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    const nativeAlert = window.alert;
    const nativeConfirm = window.confirm;
    const nativeFetch = window.fetch.bind(window);

    window.alert = (message?: unknown) => {
      const text = typeof message === 'string' ? (lang === 'en' ? translateText(message, currency) : applySelectedCurrency(message, currency)) : message;
      nativeAlert.call(window, text);
    };

    window.confirm = (message?: string) => {
      const text = typeof message === 'string' ? (lang === 'en' ? translateText(message, currency) : applySelectedCurrency(message, currency)) : message;
      return nativeConfirm.call(window, text);
    };

    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.startsWith('/api/') || url.includes('/api/')) {
        const headers = new Headers(init?.headers || (input instanceof Request ? input.headers : undefined));
        headers.set('X-SAVIA-Lang', localStorage.getItem('savia_lang') || lang);
        return nativeFetch(input, { ...init, headers });
      }
      return nativeFetch(input, init);
    };

    return () => {
      window.alert = nativeAlert;
      window.confirm = nativeConfirm;
      window.fetch = nativeFetch;
    };
  }, [lang, currency]);

  useEffect(() => {
    document.documentElement.lang = lang;

    const shouldSkip = (element: Element | null) =>
      !element || SKIP_TAGS.has(element.tagName) || Boolean(element.closest('[data-savia-i18n-ignore]'));

    const applyTextNode = (node: Text) => {
      const parent = node.parentElement;
      if (shouldSkip(parent)) return;
      const current = node.nodeValue || '';
      const lastRendered = renderedText.current.get(node);
      let original = originals.current.get(node);
      if (original === undefined) {
        original = current;
        originals.current.set(node, original);
      } else {
        const translatedOriginal = lang === 'en' ? translateText(original, currency) : applySelectedCurrency(original, currency);
        if (current !== original && current !== translatedOriginal && current !== lastRendered) {
          original = current;
          originals.current.set(node, original);
        }
      }
      const next = lang === 'en' ? translateText(original, currency) : applySelectedCurrency(original, currency);
      if (current !== next) node.nodeValue = next;
      renderedText.current.set(node, next);
    };

    const applyElementAttrs = (element: Element) => {
      if (shouldSkip(element)) return;
      for (const attr of ATTRS) {
        const current = element.getAttribute(attr);
        if (!current) continue;
        let attrMap = renderedAttrs.current.get(element);
        if (!attrMap) {
          attrMap = new Map<string, string>();
          renderedAttrs.current.set(element, attrMap);
        }
        const lastRendered = attrMap.get(attr);
        const originalAttr = `data-savia-original-${attr}`;
        if (!element.hasAttribute(originalAttr)) element.setAttribute(originalAttr, current);
        let original = element.getAttribute(originalAttr) || current;
        const translatedOriginal = lang === 'en' ? translateText(original, currency) : applySelectedCurrency(original, currency);
        if (current !== original && current !== translatedOriginal && current !== lastRendered) {
          original = current;
          element.setAttribute(originalAttr, original);
        }
        const next = lang === 'en' ? translateText(original, currency) : applySelectedCurrency(original, currency);
        if (current !== next) element.setAttribute(attr, next);
        attrMap.set(attr, next);
      }
      if (element instanceof HTMLInputElement && element.type === 'date') {
        element.setAttribute('lang', lang === 'en' ? 'en-US' : 'fr-FR');
      }
    };

    const applyTree = (root: ParentNode) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        applyTextNode(node as Text);
        node = walker.nextNode();
      }
      if (root instanceof Element) applyElementAttrs(root);
      root.querySelectorAll?.('*').forEach(applyElementAttrs);
    };

    observer.current?.disconnect();
    if (document.body) applyTree(document.body);
    observer.current = new MutationObserver(records => {
      for (const record of records) {
        if (record.type === 'characterData') applyTextNode(record.target as Text);
        record.addedNodes.forEach(node => {
          if (node.nodeType === Node.TEXT_NODE) applyTextNode(node as Text);
          if (node.nodeType === Node.ELEMENT_NODE) applyTree(node as Element);
        });
        if (record.type === 'attributes' && record.target instanceof Element) applyElementAttrs(record.target);
      }
    });
    if (document.body) {
      observer.current.observe(document.body, {
        subtree: true,
        childList: true,
        characterData: true,
        attributes: true,
        attributeFilter: ATTRS,
      });
    }
    return () => observer.current?.disconnect();
  }, [lang, currency]);

  return null;
}
