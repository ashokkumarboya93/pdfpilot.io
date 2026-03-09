/* ========================================
   PDFPilot — App Logic
   Sidebar toggle, nav, shared utilities
   ======================================== */

document.addEventListener('DOMContentLoaded', () => {

  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  const mobileToggle = document.getElementById('mobileToggle');

  // --- Sidebar Toggle ---
  function toggleSidebar() {
    if (!sidebar) return;
    const isCollapsed = sidebar.classList.toggle('collapsed');

    document.querySelectorAll('.dashboard-main, .tools-page, .history-page').forEach(el => {
      el.classList.toggle('sidebar-collapsed', isCollapsed);
    });

    localStorage.setItem('sidebarCollapsed', isCollapsed);
  }

  // Ensure sidebar is open by default on load
  if (sidebar) {
    sidebar.classList.remove('collapsed');
    document.querySelectorAll('.dashboard-main, .tools-page, .history-page').forEach(el => {
      el.classList.remove('sidebar-collapsed');
    });
    localStorage.setItem('sidebarCollapsed', 'false');
  }

  if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);

  if (mobileToggle) {
    mobileToggle.addEventListener('click', () => {
      if (window.innerWidth <= 768) {
        sidebar.classList.toggle('open');
      } else {
        toggleSidebar();
      }
    });
  }

  // Close sidebar on outside click (mobile)
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 && sidebar && sidebar.classList.contains('open')) {
      if (!sidebar.contains(e.target) && mobileToggle && !mobileToggle.contains(e.target)) {
        sidebar.classList.remove('open');
      }
    }
  });

  // --- Chat Items ---
  document.querySelectorAll('.sidebar-chat-item').forEach(item => {
    item.addEventListener('click', () => {
      document.querySelectorAll('.sidebar-chat-item').forEach(i => i.classList.remove('active'));
      item.classList.add('active');
    });
  });

  // --- Textarea Auto-Resize ---
  const chatInput = document.getElementById('chatInput');
  if (chatInput) {
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });
  }

  // --- Preview Panel Toggle ---
  const togglePreviewBtn = document.getElementById('togglePreviewBtn');
  const closePreviewBtn = document.getElementById('closePreviewBtn');
  const previewPanel = document.getElementById('previewPanel');
  const dashboardMain = document.getElementById('dashboardMain');

  function hidePreview() {
    if (previewPanel) previewPanel.classList.add('hidden');
    if (dashboardMain) dashboardMain.classList.remove('has-preview');
  }

  function showPreview() {
    if (previewPanel) previewPanel.classList.remove('hidden');
    if (dashboardMain) dashboardMain.classList.add('has-preview');
  }

  if (togglePreviewBtn) {
    togglePreviewBtn.addEventListener('click', () => {
      if (previewPanel && previewPanel.classList.contains('hidden')) {
        showPreview();
      } else {
        hidePreview();
      }
    });
  }

  if (closePreviewBtn) closePreviewBtn.addEventListener('click', hidePreview);

  // --- History Search & Filter ---
  const historySearch = document.getElementById('historySearch');
  const historyFilter = document.getElementById('historyFilter');
  const historyTable = document.getElementById('historyTable');

  if (historySearch && historyTable) {
    historySearch.addEventListener('input', () => {
      const q = historySearch.value.toLowerCase();
      historyTable.querySelectorAll('tbody tr').forEach(row => {
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }

  if (historyFilter && historyTable) {
    historyFilter.addEventListener('change', () => {
      const val = historyFilter.value.toLowerCase();
      historyTable.querySelectorAll('tbody tr').forEach(row => {
        if (val === 'all') {
          row.style.display = '';
        } else {
          const op = row.querySelectorAll('td')[1].textContent.toLowerCase();
          row.style.display = op.includes(val) ? '' : 'none';
        }
      });
    });
  }

  // --- Scroll Animations ---
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.animationPlayState = 'running';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.08 });

  document.querySelectorAll('[class*="animate-"]').forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.top > window.innerHeight) {
      el.style.animationPlayState = 'paused';
      observer.observe(el);
    }
  });

});
