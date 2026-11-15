(function (root) {
    function normalize(value) {
        return String(value || '').toLocaleLowerCase('tr-TR').replace(/ı/g, 'i')
            .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .replace(/[’'`\-‐‑–—]/g, ' ').replace(/\s+/g, ' ').trim();
    }
    function eslesir(value, answer, aliases) {
        const target = normalize(value);
        return !!target && [answer, ...(aliases || []).map(a => Array.isArray(a) ? a[0] : a)]
            .some(a => normalize(a) === target);
    }
    const api = { normalize, eslesir };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    if (root) root.CografyaNormalize = api;
})(typeof window !== 'undefined' ? window : null);
