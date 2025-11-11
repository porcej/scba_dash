// CSRF Token Helper
function getCSRFToken() {
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    return metaTag ? metaTag.getAttribute('content') : '';
}

// Helper function for fetch with CSRF token
function fetchWithCSRF(url, options = {}) {
    const token = getCSRFToken();
    options.headers = options.headers || {};
    options.headers['X-CSRFToken'] = token;
    if (!options.headers['Content-Type'] && options.method === 'POST') {
        options.headers['Content-Type'] = 'application/json';
    }
    return fetch(url, options);
}

// Theme Toggle Functionality
(function() {
    // Initialize theme from localStorage or default to light
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);

    // Theme toggle button
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function(e) {
            e.preventDefault();
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });
    }

    function updateThemeIcon(theme) {
        const themeText = document.getElementById('theme-text');
        if (themeText) {
            themeText.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
        }
    }
})();

// Socket.IO Connection
let socket = null;

function initSocketIO() {
    if (typeof io !== 'undefined') {
        // Connect to Socket.IO server
        // Socket.IO will automatically use the correct transport (websocket or polling)
        socket = io({
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionDelay: 1000,
            reconnectionAttempts: 5
        });
        
        socket.on('connect', function() {
            console.log('Socket.IO connected');
        });

        socket.on('disconnect', function() {
            console.log('Socket.IO disconnected');
        });

        // Task updates
        socket.on('task_updated', function(data) {
            console.log('Task updated:', data);
            // Handle task updates dynamically
            if (window.handleTaskUpdate) {
                window.handleTaskUpdate(data);
            } else if (window.location.pathname.includes('/tasks')) {
                loadTasks();
            } else if (window.location.pathname.includes('/dashboard')) {
                // Refresh dashboard tasks
                if (window.updateDashboardTasks) {
                    window.updateDashboardTasks(data);
                }
            }
        });

        // Scraped data updates
        socket.on('scrape_update', function(data) {
            console.log('Scrape update:', data);
            // Update dashboard if needed
            if (window.location.pathname.includes('/dashboard')) {
                // Update alerts table
                if (window.updateScrapedDataFunction) {
                    window.updateScrapedDataFunction(data);
                }
                // Update gear list if present in the update
                if (data && data.gear_list) {
                    console.log('Gear list update received:', data.gear_list);
                    if (window.renderGearListTable) {
                        window.renderGearListTable(data.gear_list);
                    }
                }
            }
        });

        // Alert updates
        socket.on('alert_update', function(data) {
            console.log('Alert update:', data);
            updateAlertBanner(data);
        });
    }
}

// Initialize Socket.IO when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSocketIO);
} else {
    initSocketIO();
}

function getAlertDefaults() {
    const defaults = window.alertDefaults || {};
    const fallbackColor = typeof defaults.color === 'string' ? defaults.color.toLowerCase() : 'danger';
    let fontSize = parseInt(defaults.fontSizePx, 10);
    if (Number.isNaN(fontSize) || fontSize < 12 || fontSize > 64) {
        fontSize = 16;
    }
    return {
        color: fallbackColor || 'danger',
        fontSize
    };
}

// Alert Banner Management
function updateAlertBanner(alertData) {
    const alertBanner = document.getElementById('alert-banner');
    const alertMessage = document.getElementById('alert-message');
    const alertBannerInner = document.getElementById('alert-banner-inner');
    const alertBannerIcon = document.getElementById('alert-banner-icon');
    
    if (!alertBanner || !alertMessage || !alertBannerInner) return;
    
    const defaults = getAlertDefaults();

    if (alertData && alertData.is_active && alertData.message) {
        alertMessage.textContent = alertData.message;
        const allowedThemes = ['primary', 'secondary', 'success', 'danger', 'warning', 'info', 'dark', 'light'];
        const selectedTheme = (alertData.color_theme || defaults.color).toLowerCase();
        const normalizedTheme = allowedThemes.includes(selectedTheme) ? selectedTheme : defaults.color;
        alertBannerInner.className = `alert alert-${normalizedTheme} alert-dismissible fade show mb-0`;
        alertBannerInner.style.fontSize = `${defaults.fontSize}px`;

        if (alertBannerIcon) {
            const iconClasses = {
                danger: 'bi-exclamation-octagon-fill',
                warning: 'bi-exclamation-triangle-fill',
                success: 'bi-check-circle-fill',
                info: 'bi-info-circle-fill',
                primary: 'bi-info-circle-fill',
                secondary: 'bi-info-circle-fill',
                dark: 'bi-info-circle-fill',
                light: 'bi-info-circle-fill'
            };
            const iconClass = iconClasses[normalizedTheme] || iconClasses[defaults.color] || 'bi-info-circle-fill';
            alertBannerIcon.className = `bi ${iconClass}`;
        }

        alertBanner.classList.remove('d-none');
        document.body.classList.add('alert-active');
    } else {
        alertBanner.classList.add('d-none');
        document.body.classList.remove('alert-active');
    }
}

// Check for active alerts on page load
function checkActiveAlerts() {
    fetchWithCSRF('/api/alerts/active')
        .then(response => response.json())
        .then(data => {
            if (data && data.alert) {
                updateAlertBanner(data.alert);
            }
        })
        .catch(error => console.error('Error checking alerts:', error));
}

// Initialize alert check
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', checkActiveAlerts);
} else {
    checkActiveAlerts();
}

// Dismiss alert button handler
document.addEventListener('DOMContentLoaded', function() {
    const dismissBtn = document.getElementById('dismiss-alert-btn');
    if (dismissBtn) {
        dismissBtn.addEventListener('click', function() {
            document.getElementById('alert-banner').classList.add('d-none');
            document.body.classList.remove('alert-active');
        });
    }
});

// Utility function to load tasks (to be implemented in tasks page)
function loadTasks() {
    // This will be implemented in the tasks page
    if (window.loadTasksFunction) {
        window.loadTasksFunction();
    }
}

// Utility function to update scraped data (to be implemented in dashboard)
function updateScrapedData(data) {
    // This will be implemented in the dashboard page
    if (window.updateScrapedDataFunction) {
        window.updateScrapedDataFunction(data);
    }
}

