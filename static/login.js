const loginForm = document.getElementById('loginForm');
const usernameInput = document.getElementById('usernameInput');
const passwordInput = document.getElementById('passwordInput');
const loginStatus = document.getElementById('loginStatus');

if (loginForm) {
    loginForm.addEventListener('submit', async event => {
        event.preventDefault();
        const username = (usernameInput?.value || '').trim().toLowerCase();
        const password = (passwordInput?.value || '').trim();
        if (!username || !password) {
            if (loginStatus) loginStatus.textContent = 'Username and password are required.';
            return;
        }

        if (usernameInput) usernameInput.value = username;

        if (window.TharaniAuth) {
            // Avoid stale tokens interfering with the current login attempt.
            window.TharaniAuth.clearAuth();
        }

        if (loginStatus) loginStatus.textContent = 'Signing in...';

        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password }),
            });
            const payload = await response.json();
            if (!response.ok) {
                if (loginStatus) loginStatus.textContent = payload.message || 'Login failed.';
                return;
            }

            if (window.TharaniAuth) {
                window.TharaniAuth.saveAuth(payload.token, payload.user);
            }

            const nextUrl = new URLSearchParams(window.location.search).get('next') || '/dashboard';
            window.location.href = nextUrl;
        } catch (_error) {
            if (loginStatus) loginStatus.textContent = 'Unable to login right now.';
        }
    });
}
