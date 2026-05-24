/**
 * App Core JS - Kế hoạch Sản xuất B7KHSX
 * API wrapper, sidebar menu, toast notifications
 */

// ==================== API Helper ====================
const api = {
    async get(url) {
        const res = await fetch(url, { credentials: 'same-origin' });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        return res.json();
    },

    async post(url, body) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(body)
        });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        return res.json();
    },

    async put(url, body) {
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify(body)
        });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        return res.json();
    },

    async upload(url, formData) {
        const res = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            body: formData
        });
        if (res.status === 401) { window.location.href = '/login'; return null; }
        const text = await res.text();
        try {
            return JSON.parse(text);
        } catch (e) {
            throw new Error(`Server ${res.status}: ${text.substring(0, 200)}`);
        }
    }
};

// ==================== Toast Notifications ====================
function showToast(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const iconMap = {
        success: 'bi-check-circle-fill',
        error: 'bi-exclamation-circle-fill',
        warning: 'bi-exclamation-triangle-fill',
        info: 'bi-info-circle-fill'
    };

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<i class="bi ${iconMap[type] || iconMap.info}"></i> ${message}`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, duration);
}

// ==================== Sidebar Menu ====================
function highlightActiveMenu() {
    const currentPath = window.location.pathname;
    const moduleToPage = {
        'PagesKDE.SanPham': '/page/sanpham',
        'PagesKDE.DatHang': '/page/dathang',
        'PagesKDE.EmailImport': '/page/nhanemail',
        'PagesKDE.TonBon': '/page/tonbon',
        'PagesKDE.Batching': '/page/batching',
        'PagesKDE.BaoBi': '/page/baobi',
        'PagesKDE.PackingPlan': '/page/packingplan',
        'PagesKDE.Pellet': '/page/pellet',
        'PagesKDE.StockOld': '/page/stockold',
        'PagesKDE.Packing': '/page/packing',
        'PagesKDE.Sale': '/page/sale',
        'PagesKDE.Plan': '/page/plan',
        'PagesKDE.StockHomNay': '/page/stockhomnay',
        'PagesKDE.LichThang': '/page/lichthang',
        'PagesKDE.GhiChu': '/page/ghichu',
        'Admin.TaoBang': '/admin/tables',
        'Admin.Users': '/admin/users',
        'Admin.VaiTro': '/admin/roles',
        'Admin.Settings': '/admin/settings',
    };

    let activeModule = null;
    for (const [mod, path] of Object.entries(moduleToPage)) {
        if (currentPath === path) {
            activeModule = mod;
            break;
        }
    }

    if (!activeModule) return;

    document.querySelectorAll('.menu-sub-item').forEach(btn => {
        if (btn.getAttribute('data-module') === activeModule) {
            btn.classList.add('active');
            const subContainer = btn.closest('.menu-sub-items');
            if (subContainer) {
                subContainer.classList.add('show');
                const header = subContainer.previousElementSibling;
                if (header) header.classList.add('expanded');
            }
        }
    });

    document.querySelectorAll('.menu-group-header').forEach(btn => {
        if (btn.getAttribute('data-module') === activeModule) {
            btn.classList.add('active');
        }
    });
}

async function loadSidebarMenu() {
    const menuContainer = document.getElementById('sidebar-menu');
    if (!menuContainer) return;

    const renderMenu = (menuData) => {
        menuContainer.innerHTML = '';
        menuData.forEach((group, idx) => {
            const groupDiv = document.createElement('div');
            groupDiv.className = 'menu-group';

            if (group.sub_functions.length === 1) {
                const sub = group.sub_functions[0];
                const header = document.createElement('button');
                header.className = 'menu-group-header';
                header.innerHTML = `<i class="bi bi-${group.icon || 'circle'}"></i> ${group.name}`;
                header.setAttribute('data-module', sub.module_path);
                header.onclick = () => navigateToModule(sub.name, sub.module_path, header);
                groupDiv.appendChild(header);
            } else {
                const header = document.createElement('button');
                header.className = 'menu-group-header expanded';
                header.innerHTML = `<i class="bi bi-${group.icon || 'circle'}"></i> ${group.name} <i class="bi bi-chevron-right menu-arrow"></i>`;
                header.onclick = () => {
                    header.classList.toggle('expanded');
                    const subItems = header.nextElementSibling;
                    if (subItems) subItems.classList.toggle('show');
                };
                groupDiv.appendChild(header);

                const subContainer = document.createElement('div');
                subContainer.className = 'menu-sub-items show';

                group.sub_functions.forEach(sub => {
                    const subBtn = document.createElement('button');
                    subBtn.className = 'menu-sub-item';
                    subBtn.textContent = sub.name;
                    subBtn.setAttribute('data-module', sub.module_path);
                    subBtn.onclick = () => navigateToModule(sub.name, sub.module_path, subBtn);
                    subContainer.appendChild(subBtn);
                });

                groupDiv.appendChild(subContainer);
            }
            menuContainer.appendChild(groupDiv);
        });
        
        highlightActiveMenu();
    };

    // 1. Try instant load from sessionStorage cache
    const cachedMenu = sessionStorage.getItem('sidebar_menu');
    if (cachedMenu) {
        try {
            const parsed = JSON.parse(cachedMenu);
            renderMenu(parsed);
        } catch (e) {
            sessionStorage.removeItem('sidebar_menu');
        }
    }

    // 2. Silently fetch from server to update cache and DOM if changed (Stale-While-Revalidate)
    try {
        const data = await api.get('/api/menu');
        if (data && data.menu) {
            const freshDataStr = JSON.stringify(data.menu);
            if (freshDataStr !== cachedMenu) {
                sessionStorage.setItem('sidebar_menu', freshDataStr);
                renderMenu(data.menu);
            }
        }
    } catch (e) {
        if (!cachedMenu) {
            menuContainer.innerHTML = '<div class="menu-loading">Lỗi tải menu</div>';
        }
    }
}

function navigateToModule(name, modulePath, clickedEl) {
    document.querySelectorAll('.menu-group-header.active, .menu-sub-item.active').forEach(el => {
        el.classList.remove('active');
    });
    clickedEl.classList.add('active');

    const breadcrumb = document.getElementById('current-page-title');
    if (breadcrumb) breadcrumb.textContent = name;

    const moduleToPage = {
        'PagesKDE.SanPham': '/page/sanpham',
        'PagesKDE.DatHang': '/page/dathang',
        'PagesKDE.EmailImport': '/page/nhanemail',
        'PagesKDE.TonBon': '/page/tonbon',
        'PagesKDE.Batching': '/page/batching',
        'PagesKDE.BaoBi': '/page/baobi',
        'PagesKDE.PackingPlan': '/page/packingplan',
        'PagesKDE.Pellet': '/page/pellet',
        'PagesKDE.StockOld': '/page/stockold',
        'PagesKDE.Packing': '/page/packing',
        'PagesKDE.Sale': '/page/sale',
        'PagesKDE.Plan': '/page/plan',
        'PagesKDE.StockHomNay': '/page/stockhomnay',
        'PagesKDE.LichThang': '/page/lichthang',
        'PagesKDE.GhiChu': '/page/ghichu',
        'Admin.TaoBang': '/admin/tables',
        'Admin.Users': '/admin/users',
        'Admin.VaiTro': '/admin/roles',
        'Admin.Settings': '/admin/settings',
    };

    if (modulePath && moduleToPage[modulePath]) {
        window.location.href = moduleToPage[modulePath];
    } else if (modulePath) {
        const content = document.getElementById('page-content');
        if (content) {
            content.innerHTML = `
                <div class="dashboard-welcome">
                    <h2><i class="bi bi-gear"></i> ${name}</h2>
                    <p class="text-muted">Chức năng "${name}" chưa được chuyển đổi sang Flask.</p>
                    <p class="text-muted">Module: ${modulePath}</p>
                </div>
            `;
        }
    }
}

// ==================== Sidebar Toggle ====================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('collapsed');
}

// ==================== Logout ====================
async function doLogout() {
    try {
        await api.post('/api/logout', {});
    } catch (e) { }
    window.location.href = '/login';
}

// ==================== DataTable Component ====================
class DataTable {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        this.refName = containerId.replace(/[^a-zA-Z0-9_]/g, '_'); // safe JS identifier
        this.apiUrl = options.apiUrl || '';
        this.editUrl = options.editUrl || '';
        this.columns = options.columns || [];
        this.searchColumns = options.searchColumns || [];
        this.onEdit = options.onEdit || null;
        this.onDelete = options.onDelete || null;
        this.editingCell = null; // track current editing cell

        this.page = 1;
        this.perPage = options.perPage || 20;
        this.search = '';
        this.data = [];
        this.total = 0;
        this.selectedIds = new Set();
        this.sortCol = null;
        this.sortDir = null;

        this.render();
    }

    render() {
        const R = this.refName; // short alias
        this.container.innerHTML = `
            <div class="table-toolbar">
                <div class="search-box">
                    <i class="bi bi-search"></i>
                    <input type="text" id="${this.container.id}-search" placeholder="Tìm kiếm..." value="${this.search}">
                </div>
                <div class="toolbar-actions">
                    <button class="btn btn-danger btn-sm" id="${this.container.id}-delete-btn" style="display:none" onclick="window._dt_${R}.deleteSelected()">
                        <i class="bi bi-trash"></i> Xóa đã chọn
                    </button>
                </div>
            </div>
            <div class="data-table-wrapper">
                <table class="data-table">
                    <thead><tr id="${this.container.id}-thead"></tr></thead>
                    <tbody id="${this.container.id}-tbody"></tbody>
                </table>
            </div>
            <div class="pagination-bar" id="${this.container.id}-pagination"></div>
        `;

        // Store reference globally for onclick handlers
        window[`_dt_${R}`] = this;

        // Search handler with debounce
        const searchInput = document.getElementById(`${this.container.id}-search`);
        let debounceTimer;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                this.search = e.target.value;
                this.page = 1;
                this.loadData();
            }, 400);
        });

        this.loadData();
    }

    async loadData() {
        const params = new URLSearchParams({
            page: this.page,
            per_page: this.perPage,
            search: this.search
        });

        try {
            const data = await api.get(`${this.apiUrl}?${params}`);
            if (!data) return;

            this.data = data.data || [];
            this.total = data.total || 0;
            this.totalPages = data.total_pages || 1;
            this.selectedIds.clear();

            this.renderTable();
            this.renderPagination();
            this.updateDeleteBtn();
        } catch (e) {
            showToast('Lỗi tải dữ liệu', 'error');
        }
    }

    renderTable() {
        // Header
        const thead = document.getElementById(`${this.container.id}-thead`);
        let headerHtml = '<th class="col-check"><input type="checkbox" onchange="window._dt_' + this.refName + '.toggleAll(this)"></th>';
        this.columns.forEach(col => {
            if (col.key === 'ID') return; // Hide ID
            headerHtml += `<th class="sortable">${col.label}</th>`;
        });
        thead.innerHTML = headerHtml;

        // Body
        const tbody = document.getElementById(`${this.container.id}-tbody`);
        if (this.data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${this.columns.length + 1}" class="text-center text-muted" style="padding:30px">Không có dữ liệu</td></tr>`;
            return;
        }

        let bodyHtml = '';
        this.data.forEach(row => {
            const rowId = row['ID'];
            const checked = this.selectedIds.has(rowId) ? 'checked' : '';
            bodyHtml += `<tr data-id="${rowId}" class="${checked ? 'selected' : ''}">`;
            bodyHtml += `<td class="col-check"><input type="checkbox" value="${rowId}" ${checked} onchange="window._dt_${this.refName}.toggleRow(this, ${rowId})"></td>`;

            this.columns.forEach(col => {
                if (col.key === 'ID') return;
                const val = row[col.key] ?? '';
                if (col.editable && this.editUrl) {
                    bodyHtml += `<td class="cell-editable" data-key="${col.key}" data-id="${rowId}" onclick="window._dt_${this.refName}.startEdit(this, ${rowId}, '${col.key}')">${this.escapeHtml(String(val))}</td>`;
                } else {
                    bodyHtml += `<td>${this.escapeHtml(String(val))}</td>`;
                }
            });

            bodyHtml += '</tr>';
        });
        tbody.innerHTML = bodyHtml;
    }

    startEdit(td, rowId, colKey) {
        // Prevent double-editing
        if (this.editingCell) this.cancelEdit();
        if (td.querySelector('input')) return;

        const oldValue = td.textContent;
        this.editingCell = { td, rowId, colKey, oldValue };

        const input = document.createElement('input');
        input.type = 'text';
        input.value = oldValue;
        input.className = 'cell-edit-input';
        input.setAttribute('data-old', oldValue);

        td.textContent = '';
        td.appendChild(input);
        td.classList.add('editing');
        input.focus();
        input.select();

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                this.saveEdit(td, rowId, colKey, input.value, oldValue);
            } else if (e.key === 'Escape') {
                this.cancelEdit();
            }
        });

        input.addEventListener('blur', () => {
            // Small delay to allow Enter key handler to fire first
            setTimeout(() => {
                if (this.editingCell && this.editingCell.td === td) {
                    this.saveEdit(td, rowId, colKey, input.value, oldValue);
                }
            }, 100);
        });
    }

    async saveEdit(td, rowId, colKey, newValue, oldValue) {
        this.editingCell = null;
        td.classList.remove('editing');

        // If no change, restore
        if (newValue === oldValue) {
            td.textContent = oldValue;
            return;
        }

        td.textContent = newValue;
        td.classList.add('cell-saving');

        try {
            const body = {};
            body[colKey] = newValue;
            const result = await api.put(`${this.editUrl}/${rowId}`, body);
            td.classList.remove('cell-saving');

            if (result && result.success) {
                td.classList.add('cell-saved');
                setTimeout(() => td.classList.remove('cell-saved'), 1200);
                // Update local data
                const row = this.data.find(r => r['ID'] === rowId);
                if (row) row[colKey] = newValue;
            } else {
                td.textContent = oldValue;
                showToast(result?.message || 'Lỗi cập nhật', 'error');
            }
        } catch (e) {
            td.classList.remove('cell-saving');
            td.textContent = oldValue;
            showToast('Lỗi kết nối', 'error');
        }
    }

    cancelEdit() {
        if (!this.editingCell) return;
        const { td, oldValue } = this.editingCell;
        td.classList.remove('editing');
        td.textContent = oldValue;
        this.editingCell = null;
    }

    renderPagination() {
        const pag = document.getElementById(`${this.container.id}-pagination`);
        const from = (this.page - 1) * this.perPage + 1;
        const to = Math.min(this.page * this.perPage, this.total);

        let pagHtml = `
            <div class="pagination-info">
                Hiển thị ${from}-${to} / ${this.total} bản ghi
                &nbsp;|&nbsp;
                <select onchange="window._dt_${this.refName}.changePerPage(this.value)">
                    ${[10, 20, 50, 100].map(n => `<option value="${n}" ${n === this.perPage ? 'selected' : ''}>${n}/trang</option>`).join('')}
                </select>
            </div>
            <div class="pagination-controls">
                <button ${this.page <= 1 ? 'disabled' : ''} onclick="window._dt_${this.refName}.goToPage(1)">«</button>
                <button ${this.page <= 1 ? 'disabled' : ''} onclick="window._dt_${this.refName}.goToPage(${this.page - 1})">‹</button>
        `;

        // Page buttons
        const maxButtons = 5;
        let startPage = Math.max(1, this.page - Math.floor(maxButtons / 2));
        let endPage = Math.min(this.totalPages, startPage + maxButtons - 1);
        startPage = Math.max(1, endPage - maxButtons + 1);

        for (let i = startPage; i <= endPage; i++) {
            pagHtml += `<button class="${i === this.page ? 'current-page' : ''}" onclick="window._dt_${this.refName}.goToPage(${i})">${i}</button>`;
        }

        pagHtml += `
                <button ${this.page >= this.totalPages ? 'disabled' : ''} onclick="window._dt_${this.refName}.goToPage(${this.page + 1})">›</button>
                <button ${this.page >= this.totalPages ? 'disabled' : ''} onclick="window._dt_${this.refName}.goToPage(${this.totalPages})">»</button>
            </div>
        `;
        pag.innerHTML = pagHtml;
    }

    toggleAll(checkbox) {
        const checkboxes = document.querySelectorAll(`#${this.container.id}-tbody input[type="checkbox"]`);
        checkboxes.forEach(cb => {
            cb.checked = checkbox.checked;
            const id = parseInt(cb.value);
            if (checkbox.checked) {
                this.selectedIds.add(id);
            } else {
                this.selectedIds.delete(id);
            }
            cb.closest('tr').classList.toggle('selected', checkbox.checked);
        });
        this.updateDeleteBtn();
    }

    toggleRow(checkbox, id) {
        if (checkbox.checked) {
            this.selectedIds.add(id);
        } else {
            this.selectedIds.delete(id);
        }
        checkbox.closest('tr').classList.toggle('selected', checkbox.checked);
        this.updateDeleteBtn();
    }

    updateDeleteBtn() {
        const btn = document.getElementById(`${this.container.id}-delete-btn`);
        if (btn) {
            btn.style.display = this.selectedIds.size > 0 ? 'inline-flex' : 'none';
            btn.innerHTML = `<i class="bi bi-trash"></i> Xóa (${this.selectedIds.size})`;
        }
    }

    async deleteSelected() {
        if (this.selectedIds.size === 0) return;
        if (!confirm(`Bạn có chắc muốn xóa ${this.selectedIds.size} bản ghi?`)) return;

        if (this.onDelete) {
            await this.onDelete([...this.selectedIds]);
        }
    }

    goToPage(page) {
        this.page = page;
        this.loadData();
    }

    changePerPage(val) {
        this.perPage = parseInt(val);
        this.page = 1;
        this.loadData();
    }

    escapeHtml(text) {
        const el = document.createElement('span');
        el.textContent = text;
        return el.innerHTML;
    }
}
