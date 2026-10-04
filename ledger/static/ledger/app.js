'use strict';
document.querySelectorAll('form[data-unsaved]').forEach(form => {
  let dirty = false;
  form.addEventListener('input', () => { dirty = true; });
  form.addEventListener('change', () => { dirty = true; });
  form.addEventListener('submit', () => { dirty = false; });
  window.addEventListener('beforeunload', event => {
    if (dirty) { event.preventDefault(); event.returnValue = ''; }
  });
  document.querySelectorAll('a[href]').forEach(link => {
    link.addEventListener('click', event => {
      if (dirty && !link.hasAttribute('target')) {
        if (!window.confirm('You have unsaved changes. Leave this page and discard them?')) event.preventDefault();
        else dirty = false;
      }
    });
  });
});
document.getElementById('print-report')?.addEventListener('click', () => window.print());
document.querySelectorAll('[data-copy]').forEach(button => {
  button.addEventListener('click', async () => {
    const input = document.getElementById(button.dataset.copy);
    const status = document.getElementById('copy-status');
    try { await navigator.clipboard.writeText(input.value); status.textContent = 'Source copied.'; }
    catch { input.focus(); input.select(); status.textContent = 'Select and copy the source with your keyboard.'; }
  });
});
document.querySelector('.error-summary')?.focus();
