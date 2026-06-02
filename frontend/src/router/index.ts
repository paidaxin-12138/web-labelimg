import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: () => import('@/views/LoginView.vue') },
    { path: '/', component: () => import('@/views/ProjectsView.vue'), meta: { auth: true } },
    { path: '/projects/:id', component: () => import('@/views/AnnotateView.vue'), meta: { auth: true } },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.auth && !auth.isAuthenticated) return '/login'
  if (auth.isAuthenticated && !auth.user) {
    try { await auth.fetchMe() } catch { auth.logout(); return '/login' }
  }
  return true
})

export default router
