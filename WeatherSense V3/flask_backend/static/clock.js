const navClockTimeEl = document.getElementById('nav-clock-time');
const navClockDateEl = document.getElementById('nav-clock-date');

function updateNavClock() {
    const now = new Date();

    if (navClockTimeEl) {
        navClockTimeEl.textContent = now.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    if (navClockDateEl) {
        navClockDateEl.textContent = now.toLocaleDateString([], {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
            year: 'numeric',
            timeZoneName: 'short'
        });
    }
}

updateNavClock();
setInterval(updateNavClock, 1000);
