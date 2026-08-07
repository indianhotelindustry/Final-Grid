// Guest Search Autocomplete
class GuestSearch {
    constructor(inputId, onSelect) {
        this.input = document.getElementById(inputId);
        this.onSelect = onSelect;
        this.dropdown = null;
        this.selectedIndex = -1;
        this.results = [];
        this.debounceTimer = null;
        
        this.init();
    }
    
    init() {
        if (!this.input) return;

        // Wrap the entire input-group (not just the input) so Bootstrap's
        // flexbox layout is preserved and the icon stays on the same row.
        const inputGroup = this.input.closest('.input-group') || this.input.parentNode;
        const wrapper = document.createElement('div');
        wrapper.className = 'guest-search-wrapper';
        inputGroup.parentNode.insertBefore(wrapper, inputGroup);
        wrapper.appendChild(inputGroup);
        this.wrapper = wrapper;

        this.dropdown = document.createElement('div');
        this.dropdown.className = 'guest-search-dropdown';
        wrapper.appendChild(this.dropdown);
        
        // Event listeners
        this.input.addEventListener('input', () => this.handleInput());
        this.input.addEventListener('keydown', (e) => this.handleKeydown(e));
        document.addEventListener('click', (e) => this.handleClickOutside(e));
    }
    
    handleInput() {
        clearTimeout(this.debounceTimer);
        const query = this.input.value.trim();
        
        if (query.length < 2) {
            this.hideDropdown();
            return;
        }
        
        this.debounceTimer = setTimeout(() => this.search(query), 300);
    }
    
    async search(query) {
        try {
            const response = await fetch(`/api/search-guests?q=${encodeURIComponent(query)}`);
            this.results = await response.json();
            this.renderResults();
        } catch (error) {
            console.error('Guest search error:', error);
        }
    }
    
    renderResults() {
        if (this.results.length === 0) {
            this.dropdown.innerHTML = '<div class="guest-search-no-results">Guest Not Found in Database</div>';
            this.showDropdown();
            return;
        }
        
        this.dropdown.innerHTML = this.results.map((guest, index) => `
            <div class="guest-search-item" data-index="${index}">
                <div class="guest-search-name">${escapeHtml(guest.name)}</div>
                <div class="guest-search-details">
                    ${escapeHtml(guest.phone)} | ${escapeHtml(guest.company || 'No Company')} | ${escapeHtml(guest.folio_no)}
                </div>
            </div>
        `).join('');
        
        this.dropdown.querySelectorAll('.guest-search-item').forEach(item => {
            item.addEventListener('click', () => {
                const index = parseInt(item.dataset.index);
                this.selectGuest(this.results[index]);
            });
        });
        
        this.showDropdown();
        this.selectedIndex = -1;
    }
    
    handleKeydown(e) {
        if (!this.dropdown.classList.contains('show')) return;
        
        const items = this.dropdown.querySelectorAll('.guest-search-item');
        
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this.selectedIndex = Math.min(this.selectedIndex + 1, items.length - 1);
            this.highlightItem(items);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
            this.highlightItem(items);
        } else if (e.key === 'Enter' && this.selectedIndex >= 0) {
            e.preventDefault();
            this.selectGuest(this.results[this.selectedIndex]);
        } else if (e.key === 'Escape') {
            this.hideDropdown();
        }
    }
    
    highlightItem(items) {
        items.forEach((item, index) => {
            item.classList.toggle('active', index === this.selectedIndex);
        });
    }
    
    selectGuest(guest) {
        this.input.value = guest.name;
        this.hideDropdown();
        if (this.onSelect) {
            this.onSelect(guest);
        }
    }
    
    handleClickOutside(e) {
        if (!this.wrapper.contains(e.target)) {
            this.hideDropdown();
        }
    }
    
    showDropdown() {
        this.dropdown.classList.add('show');
    }
    
    hideDropdown() {
        this.dropdown.classList.remove('show');
        this.selectedIndex = -1;
    }
}
