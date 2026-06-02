import { defineStore } from 'pinia'

export const useUiStore = defineStore('ui', {
  state: () => ({
    theme: (localStorage.getItem('theme') as 'light' | 'dark') || 'light',
    showShortcuts: false,
  }),
  actions: {
    toggleTheme() {
      this.theme = this.theme === 'light' ? 'dark' : 'light'
      localStorage.setItem('theme', this.theme)
      document.documentElement.setAttribute('data-theme', this.theme)
    },
    initTheme() {
      document.documentElement.setAttribute('data-theme', this.theme)
    },
    toggleShortcuts() {
      this.showShortcuts = !this.showShortcuts
    },
  },
})
