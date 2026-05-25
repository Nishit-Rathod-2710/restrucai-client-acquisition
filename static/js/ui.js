/*
 * Shared modern UI popups for the dashboard.
 *   UI.confirm({ title, message, confirmText, cancelText, danger }) -> Promise<boolean>
 *   UI.toast(message, type)   // type: 'success' | 'error' | 'info'
 *   UI.alert(message, type)   // toast alias for one-off messages
 * DOM + styles are created on demand; no markup needed in templates.
 */
(function () {
    'use strict';

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    const ICONS = {
        success: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>',
        error:   '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        info:    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>',
    };

    const UI = {
        confirm(opts) {
            opts = opts || {};
            const title = opts.title || 'Please confirm';
            const message = opts.message || '';
            const confirmText = opts.confirmText || 'Confirm';
            const cancelText = opts.cancelText || 'Cancel';
            const danger = !!opts.danger;

            return new Promise((resolve) => {
                const overlay = document.createElement('div');
                overlay.className = 'ui-modal-overlay';
                overlay.innerHTML = `
                    <div class="ui-modal" role="dialog" aria-modal="true">
                        <div class="ui-modal-icon ${danger ? 'danger' : ''}">
                            ${danger ? ICONS.error : ICONS.info}
                        </div>
                        <h3 class="ui-modal-title">${esc(title)}</h3>
                        <p class="ui-modal-msg">${esc(message)}</p>
                        <div class="ui-modal-actions">
                            <button class="ui-btn ui-btn-ghost" data-act="cancel">${esc(cancelText)}</button>
                            <button class="ui-btn ${danger ? 'ui-btn-danger' : 'ui-btn-primary'}" data-act="ok">${esc(confirmText)}</button>
                        </div>
                    </div>`;
                document.body.appendChild(overlay);
                requestAnimationFrame(() => overlay.classList.add('open'));

                const close = (val) => {
                    overlay.classList.remove('open');
                    document.removeEventListener('keydown', onKey);
                    setTimeout(() => overlay.remove(), 200);
                    resolve(val);
                };
                const onKey = (e) => {
                    if (e.key === 'Escape') close(false);
                    if (e.key === 'Enter') close(true);
                };
                overlay.addEventListener('click', (e) => {
                    if (e.target === overlay) close(false);
                    const act = e.target.closest('[data-act]')?.dataset.act;
                    if (act === 'ok') close(true);
                    if (act === 'cancel') close(false);
                });
                document.addEventListener('keydown', onKey);
                setTimeout(() => overlay.querySelector('[data-act="ok"]').focus(), 60);
            });
        },

        toast(message, type) {
            type = type || 'info';
            let host = document.getElementById('ui-toast-host');
            if (!host) {
                host = document.createElement('div');
                host.id = 'ui-toast-host';
                document.body.appendChild(host);
            }
            const el = document.createElement('div');
            el.className = `ui-toast ${type}`;
            el.innerHTML = `<span class="ui-toast-icon">${ICONS[type] || ICONS.info}</span><span>${esc(message)}</span>`;
            host.appendChild(el);
            requestAnimationFrame(() => el.classList.add('show'));
            const remove = () => {
                el.classList.remove('show');
                setTimeout(() => el.remove(), 220);
            };
            el.addEventListener('click', remove);
            setTimeout(remove, type === 'error' ? 5000 : 3500);
        },

        alert(message, type) { this.toast(message, type || 'info'); },
    };

    window.UI = UI;
})();
