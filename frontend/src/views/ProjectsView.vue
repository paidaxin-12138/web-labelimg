<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'

const auth = useAuthStore()
const projectStore = useProjectStore()
const ui = useUiStore()
const router = useRouter()
const newName = ref('')

onMounted(async () => {
  await projectStore.loadProjects()
})

async function createProject() {
  if (!newName.value.trim()) return
  const p = await projectStore.createProject(newName.value.trim())
  newName.value = ''
  router.push(`/projects/${p.id}`)
}
</script>

<template>
  <div class="page">
    <header>
      <h2>项目列表</h2>
      <div class="actions">
        <button @click="ui.toggleTheme">切换主题</button>
        <button @click="auth.logout(); router.push('/login')">退出</button>
      </div>
    </header>
    <div class="create card">
      <input v-model="newName" placeholder="新项目名称" @keyup.enter="createProject" />
      <button @click="createProject">创建项目</button>
    </div>
    <div class="grid">
      <div v-for="p in projectStore.projects" :key="p.id" class="card project" @click="router.push(`/projects/${p.id}`)">
        <h3>{{ p.name }}</h3>
        <p>{{ p.description || '无描述' }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 24px; }
header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.actions { display: flex; gap: 8px; }
.create { display: flex; gap: 8px; margin-bottom: 16px; }
.create input { flex: 1; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.project { cursor: pointer; }
.project:hover { border-color: var(--accent); }
</style>
