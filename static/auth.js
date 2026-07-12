(function () {
    const ROLE_RANK = { operator: 1, owner: 2, officer: 3, admin: 4 };
    const AUTH_TOKEN_KEY = 'tharani_auth_token';
    const AUTH_USER_KEY = 'tharani_auth_user';

    function getStoredToken() {
        return localStorage.getItem(AUTH_TOKEN_KEY) || '';
    }

    function getStoredUser() {
        try {
            return JSON.parse(localStorage.getItem(AUTH_USER_KEY) || '{}');
        } catch {
            return {};
        }
    }

    function clearAuth() {
        localStorage.removeItem(AUTH_TOKEN_KEY);
        localStorage.removeItem(AUTH_USER_KEY);
    }

    function saveAuth(token, user) {
        localStorage.setItem(AUTH_TOKEN_KEY, token || '');
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user || {}));
    }

    function isProtectedApi(pathname) {
        return pathname.startsWith('/api/') || pathname === '/gps' || pathname === '/camera' || pathname.startsWith('/export/');
    }

    const originalFetch = window.fetch.bind(window);
    window.fetch = async function patchedFetch(input, init) {
        const options = init ? { ...init } : {};
        const headers = new Headers(options.headers || {});

        let urlObj = null;
        try {
            urlObj = new URL(typeof input === 'string' ? input : input.url, window.location.origin);
        } catch {
            urlObj = null;
        }

        const token = getStoredToken();
        if (urlObj && urlObj.origin === window.location.origin && isProtectedApi(urlObj.pathname) && token) {
            headers.set('Authorization', `Bearer ${token}`);
        }

        options.headers = headers;
        const response = await originalFetch(input, options);

        if (response.status === 401 && window.location.pathname !== '/login') {
            clearAuth();
            const next = encodeURIComponent(window.location.pathname + window.location.search);
            window.location.href = `/login?next=${next}`;
        }

        return response;
    };

    function applyNavVisibility() {
        const user = getStoredUser();
        const role = String(user.role || '').toLowerCase();
        const roleRank = ROLE_RANK[role] || 0;

        document.querySelectorAll('[data-role-min]').forEach(el => {
            const minRole = String(el.getAttribute('data-role-min') || '').toLowerCase();
            const minRank = ROLE_RANK[minRole] || 0;
            el.style.display = roleRank >= minRank ? '' : 'none';
        });

        const badge = document.getElementById('authUserBadge');
        if (badge) {
            badge.textContent = user.username ? `${user.username} (${role})` : '';
        }

        const loginLink = document.getElementById('loginNavLink');
        const logoutBtn = document.getElementById('logoutBtn');
        if (loginLink) loginLink.style.display = user.username ? 'none' : '';
        if (logoutBtn) logoutBtn.style.display = user.username ? '' : 'none';
    }

    async function hydrateAuthUser() {
        const token = getStoredToken();
        if (!token) {
            applyNavVisibility();
            return;
        }
        try {
            const response = await originalFetch('/api/auth/me', {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!response.ok) {
                clearAuth();
                applyNavVisibility();
                return;
            }
            const payload = await response.json();
            if (payload.user) saveAuth(token, payload.user);
        } catch {
            // Keep local auth snapshot until server is reachable.
        }
        applyNavVisibility();
    }

    function wireLogout() {
        const logoutBtn = document.getElementById('logoutBtn');
        if (!logoutBtn) return;
        logoutBtn.addEventListener('click', async () => {
            try {
                await originalFetch('/api/auth/logout', { method: 'POST' });
            } catch {
                // Continue local cleanup even if network call fails.
            }
            clearAuth();
            window.location.href = '/login';
        });
    }

    window.TharaniAuth = {
        saveAuth,
        clearAuth,
        getStoredUser,
        getStoredToken,
    };

    hydrateAuthUser();
    wireLogout();
})();
