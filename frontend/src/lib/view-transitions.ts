/**
 * Verifica se o usuário prefere movimento reduzido no navegador.
 * Regras: WCAG 2.1 AA e ADR-011 (Seção 2.8).
 */
export function isReducedMotionPreferred(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Dispara uma transição de visualização (View Transition) segura,
 * respeitando estritamente a preferência do usuário por movimento reduzido
 * (`prefers-reduced-motion: reduce`) e prevenindo erros em ambientes sem suporte.
 *
 * @see docs/adrs/ADR-011-arquitetura-frontend.md (Seção 2.8)
 */
export function startSafeViewTransition(callback: () => void): void {
  if (
    !isReducedMotionPreferred() &&
    typeof document !== "undefined" &&
    "startViewTransition" in document
  ) {
    document.startViewTransition(callback);
  } else {
    callback();
  }
}
