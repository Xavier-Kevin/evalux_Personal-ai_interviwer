// Global error handling
window.addEventListener('error', function(e) {
  console.error("Global JS error:", e);
});
window.addEventListener('unhandledrejection', function(e) {
  console.error("Unhandled promise rejection:", e);
});

// ==============================================
// NEW API CLIENT (for interview.html)
// ==============================================
const API_URL = 'http://127.0.0.1:8000';

const App = {
  async startInterview(topic = 'Software Development', cvSkills = []) {
    const token = localStorage.getItem('evalux_token');
    
    const response = await fetch(`${API_URL}/api/interview/start`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ topic, cv_skills: cvSkills })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to start interview');
    }
    
    return await response.json();
  },

  async sendMessage(sessionId, message) {
    const token = localStorage.getItem('evalux_token');
    
    const response = await fetch(`${API_URL}/api/interview/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        message: message,
        session_id: sessionId
      })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to send message');
    }
    
    return await response.json();
  },

  async endInterview(sessionId) {
    const token = localStorage.getItem('evalux_token');
    
    const response = await fetch(`${API_URL}/api/interview/end/${sessionId}`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to end interview');
    }
    
    return await response.json();
  }
};

window.App = App;

// ==============================================
// OLD EVALUX APP (for other pages)
// ==============================================
class EvaluxApp {
  constructor() {
    this.currentUser = null;
    this.theme = 'dark'; // Default to dark theme
    this.init();
  }

  init() {
    this.loadUser();
    this.bindUI();
    this.loadTheme();
    this.updateAuthUI();
    this.testBackend();
  }

  loadUser() {
    const raw = localStorage.getItem('evalux_user');
    if (raw) this.currentUser = JSON.parse(raw);
  }

  saveUser() {
    if (this.currentUser) localStorage.setItem('evalux_user', JSON.stringify(this.currentUser));
    else localStorage.removeItem('evalux_user');
  }

  bindUI() {
    document.getElementById('loginBtn')?.addEventListener('click', (e) => {
      e.preventDefault();
      window.location.href = 'profile.html';
    });

    document.getElementById('getStartedBtn')?.addEventListener('click', () => 
      window.location.href = this.currentUser ? 'dashboard.html' : 'profile.html'
    );

    document.querySelectorAll('.interest-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        btn.classList.toggle('selected');
        this.updateHiddenInterests();
      });
    });

    document.getElementById('goToRegister')?.addEventListener('click', (e) => { 
      e.preventDefault(); 
      window.location.href = 'profile.html'; 
    });
    
    document.getElementById('goToLogin')?.addEventListener('click', (e) => { 
      e.preventDefault(); 
      window.location.href = 'profile.html'; 
    });

    // Register handler
    document.getElementById('registerForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = (document.getElementById('regUsername')?.value || '').trim();
      const email = (document.getElementById('regEmail')?.value || '').trim();
      const password = (document.getElementById('regPassword')?.value || '');
      const interests = Array.from(document.querySelectorAll('.interest-chip.selected')).map(b => b.dataset.value);

      if (!username || username.length < 3) return this.showToast('Username must be 3+ chars', 'error');
      if (!email || !/.+@.+\..+/.test(email)) return this.showToast('Enter a valid email', 'error');
      if (!password || password.length < 6) return this.showToast('Password must be 6+ chars', 'error');
      if (password.length > 72) return this.showToast('Password cannot be longer than 72 characters', 'error');

      try {
        const res = await fetch('http://127.0.0.1:8000/register', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ username, email, password, interests })
        });
        
        if (res.ok) {
          this.showToast('Registered. Please sign in.', 'success');
          window.location.href = 'profile.html';
        } else {
          const errData = await res.json();
          this.showToast(errData.detail || errData.message || 'Registration failed', 'error');
        }
      } catch (err) {
        console.error(err);
        this.showToast('Server error during registration', 'error');
      }
    });

    // Login handler
    document.getElementById('loginForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const emailInput = document.getElementById('loginEmail') || document.getElementById('email');
      const passwordInput = document.getElementById('loginPassword') || document.getElementById('password');
      const email = (emailInput?.value || '').trim();
      const password = (passwordInput?.value || '');
      
      if (!email || !password) return this.showToast('Enter email and password', 'error');
      
      try {
        this.showToast('Logging in, please wait...', 'info');
        const formBody = new URLSearchParams();
        formBody.append('username', email);
        formBody.append('password', password);
        
        const res = await fetch('http://127.0.0.1:8000/token', {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: formBody.toString()
        });
        
        const data = await res.json();
        
        if (res.ok && data.access_token) {
          // Store token
          localStorage.setItem('evalux_token', data.access_token);
          
          // Fetch user info
          let username = '';
          try {
            const meRes = await fetch('http://127.0.0.1:8000/me', {
              headers: { 'Authorization': 'Bearer ' + data.access_token }
            });
            if (meRes.ok) {
              const meData = await meRes.json();
              username = meData.username || '';
            }
          } catch (meErr) {
            console.error('Failed to fetch user info:', meErr);
          }
          
          this.currentUser = { email, token: data.access_token, username };
          this.saveUser();
          this.updateAuthUI();
          this.showToast('Login successful', 'success');
          window.location.href = 'dashboard.html';
        } else {
          this.currentUser = null;
          this.saveUser();
          this.showToast(data.detail || data.message || 'Invalid credentials', 'error');
        }
      } catch (err) {
        this.currentUser = null;
        this.saveUser();
        console.error(err);
        this.showToast('Server error during login', 'error');
      }
    });

    // Logout
    document.getElementById('logoutBtn')?.addEventListener('click', () => {
      this.currentUser = null;
      this.saveUser();
      localStorage.removeItem('evalux_token');
      this.updateAuthUI();
      window.location.href = 'profile.html';
      this.showToast('Logged out', 'success');
    });

    // ✅ REMOVED: CV upload handlers (now in cv.html inline script)
    // No more duplicate browseBtn listener

    // Theme toggle
    document.getElementById('themeToggle')?.addEventListener('click', () => {
      this.theme = (this.theme === 'dark') ? 'light' : 'dark';
      this.applyTheme();
      this.saveTheme();
    });
  }

  updateHiddenInterests() {
    const selected = Array.from(document.querySelectorAll('.interest-chip.selected')).map(b => b.dataset.value);
    const hidden = document.getElementById('regInterests');
    if (hidden) hidden.value = selected.join(',');
  }

  updateAuthUI() {
    const userInfo = document.getElementById('userInfo');
    const authButtons = document.getElementById('authButtons');
    const userName = document.getElementById('userName');
    
    if (this.currentUser) {
      if (userInfo) userInfo.style.display = 'flex';
      if (authButtons) authButtons.style.display = 'none';
      if (userName) userName.textContent = `Welcome, ${this.currentUser.username || ''}!`;
    } else {
      if (userInfo) userInfo.style.display = 'none';
      if (authButtons) authButtons.style.display = 'flex';
    }
  }

  showToast(msg, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const t = document.createElement('div');
    t.className = `toast ${type}`;
    t.textContent = msg;
    container.appendChild(t);
    setTimeout(() => t.remove(), 3500);
  }

  drawProgressChart() {
    const canvas = document.getElementById('progressChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    const dpr = window.devicePixelRatio || 1;
    const cssW = canvas.getAttribute('width') ? Number(canvas.getAttribute('width')) : canvas.clientWidth;
    const cssH = canvas.getAttribute('height') ? Number(canvas.getAttribute('height')) : canvas.clientHeight || 360;
    canvas.width = cssW * dpr;
    canvas.height = cssH * dpr;
    canvas.style.width = cssW + 'px';
    canvas.style.height = cssH + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const labels = ['Week 1','Week 2','Week 3','Week 4','Week 5','Week 6','Week 7'];
    const data = [65, 70, 75, 80, 85, 88, 92];

    ctx.clearRect(0, 0, cssW, cssH);

    const padding = 50;
    const chartW = cssW - padding * 2;
    const chartH = cssH - padding * 2;
    const maxVal = 100;

    ctx.strokeStyle = '#eef2f7';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
      const y = padding + (chartH * i / 5);
      ctx.beginPath();
      ctx.moveTo(padding, y);
      ctx.lineTo(padding + chartW, y);
      ctx.stroke();
    }

    ctx.beginPath();
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#2563eb';
    data.forEach((v, i) => {
      const x = padding + (chartW * i / (data.length - 1));
      const y = padding + chartH - (chartH * v / maxVal);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.stroke();

    ctx.fillStyle = '#2563eb';
    data.forEach((v, i) => {
      const x = padding + (chartW * i / (data.length - 1));
      const y = padding + chartH - (chartH * v / maxVal);
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.fillStyle = '#475569';
    ctx.font = '12px Inter, sans-serif';
    ctx.textAlign = 'center';
    labels.forEach((lab, i) => {
      const x = padding + (chartW * i / (labels.length - 1));
      ctx.fillText(lab, x, padding + chartH + 20);
    });

    ctx.textAlign = 'right';
    for (let i = 0; i <= 5; i++) {
      const val = Math.round(maxVal * (5 - i) / 5);
      const y = padding + (chartH * i / 5);
      ctx.fillText(val + '%', padding - 10, y + 4);
    }
  }

  testBackend() {
    fetch('http://127.0.0.1:8000/health')
      .then(r => {
        if (!r.ok) throw new Error('Health check failed');
        return r.json();
      })
      .then(d => console.log('✅ Backend connected:', d))
      .catch(e => console.warn('⚠️ Backend unreachable:', e));
  }

  applyTheme() {
    if (this.theme === 'dark') {
      document.body.classList.add('dark');
    } else {
      document.body.classList.remove('dark');
    }

    const themeBtn = document.getElementById('themeToggle');
    if (themeBtn) {
      themeBtn.textContent = this.theme === 'dark' ? '☀️' : '🌙';
    }
  }

  saveTheme() {
    try {
      localStorage.setItem('evalux_theme', this.theme);
    } catch (e) { /* ignore */ }
  }

  loadTheme() {
    // Force dark theme always
    this.theme = 'dark';
    localStorage.setItem('evalux_theme', 'dark');
    this.applyTheme();
  }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
  window.evaluxApp = new EvaluxApp();
  console.log('✅ App.js loaded - API endpoints configured');
});