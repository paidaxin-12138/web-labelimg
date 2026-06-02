<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api from '@/services/api'
import AnnotationCanvas from '@/components/canvas/AnnotationCanvas.vue'
import { useAnnotationStore } from '@/stores/annotation'
import { useAuthStore } from '@/stores/auth'
import { useCollaborationStore } from '@/stores/collaboration'
import { useProjectStore } from '@/stores/project'
import { useUiStore } from '@/stores/ui'

const route = useRoute()
const auth = useAuthStore()
const projectStore = useProjectStore()
const annotationStore = useAnnotationStore()
const collab = useCollaborationStore()
const ui = useUiStore()
const projectId = computed(() => route.params.id as string)
const currentImageId = ref<string | null>(null)
const saving = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

onMounted(async () => {
  await projectStore.selectProject(projectId.value)
  const token = localStorage.getItem('access_token') || ''
  const ws = collab.connect(projectId.value, token)
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    if (msg.type === 'lock_status') collab.isEditor = !!msg.payload.is_editor
    if (msg.type === 'cursor_move') {
      collab.remoteCursors[msg.sender.user_id] = {
        user_id: msg.sender.user_id,
        display_name: msg.sender.display_name,
        x: msg.payload.x,
        y: msg.payload.y,
      }
    }
    if (msg.type?.startsWith('annotation_')) {
      annotationStore.applyRemote(msg.type, msg.payload)
    }
    if (msg.type === 'presence') collab.onlineUsers = msg.payload.online_users || []
  }
  window.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  collab.disconnect()
  window.removeEventListener('keydown', onKeyDown)
})

watch(currentImageId, async (id, prev) => {
  if (prev) collab.leaveImage(prev)
  if (!id) return
  collab.joinImage(id)
  const image = projectStore.images.find((i) => i.id === id)
  if (!image) return
  const { data } = await api.get(`/images/${id}/annotations`)
  const anns = (data.data?.annotations || []).filter((a: { type: string }) => a.type === 'bbox')
  annotationStore.setFromServer({
    imageId: id,
    imageWidth: image.width,
    imageHeight: image.height,
    imageUrl: image.url || '',
    baseVersion: data.version,
    annotations: anns,
  })
  annotationStore.readOnly = !collab.isEditor
  if (projectStore.labels[0]) annotationStore.currentLabelId = projectStore.labels[0].id
})

async function save() {
  if (!currentImageId.value || annotationStore.readOnly) return
  saving.value = true
  try {
    const payload = {
      base_version: annotationStore.baseVersion,
      data: {
        schema_version: 2,
        image_id: currentImageId.value,
        image_width: annotationStore.imageWidth,
        image_height: annotationStore.imageHeight,
        annotations: annotationStore.annotations,
      },
    }
    const { data } = await api.put(`/images/${currentImageId.value}/annotations`, payload)
    annotationStore.baseVersion = data.version
    alert('保存成功')
  } catch (e: unknown) {
    alert('保存失败或版本冲突')
  } finally {
    saving.value = false
  }
}

async function exportYolo() {
  const job = await projectStore.exportYolo(projectId.value)
  alert(`导出任务已创建: ${job.id}`)
}

function onUpload(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) projectStore.uploadImages(projectId.value, input.files)
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === '?' && !e.ctrlKey) { ui.toggleShortcuts(); return }
  if (e.ctrlKey && e.key.toLowerCase() === 'z') { e.preventDefault(); annotationStore.undo() }
  if (e.ctrlKey && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'))) {
    e.preventDefault(); annotationStore.redo()
  }
  if (e.ctrlKey && e.key.toLowerCase() === 's') { e.preventDefault(); save() }
}
</script>

<template>
  <div class="annotate">
    <header>
      <div>
        <strong>{{ projectStore.currentProject?.name }}</strong>
        <span class="meta">在线 {{ collab.onlineUsers.length }} · {{ collab.isEditor ? '主编辑' : '只读' }}</span>
      </div>
      <div class="actions">
        <button @click="ui.toggleTheme">主题</button>
        <button @click="fileInput?.click()">上传</button>
        <input ref="fileInput" type="file" multiple accept="image/*" hidden @change="onUpload" />
        <button :disabled="saving || annotationStore.readOnly" @click="save">保存</button>
        <button @click="exportYolo">导出 YOLO</button>
      </div>
    </header>
    <div class="body">
      <aside>
        <h4>图像 ({{ projectStore.imageTotal }})</h4>
        <div class="image-list">
          <div
            v-for="img in projectStore.images"
            :key="img.id"
            class="image-item"
            :class="{ active: currentImageId === img.id }"
            @click="currentImageId = img.id"
          >
            {{ img.filename }}
          </div>
        </div>
        <h4>标签</h4>
        <div class="labels">
          <button
            v-for="label in projectStore.labels"
            :key="label.id"
            :style="{ borderColor: label.color }"
            :class="{ active: annotationStore.currentLabelId === label.id }"
            @click="annotationStore.currentLabelId = label.id"
          >
            {{ label.name }}
          </button>
        </div>
        <div class="tools">
          <button :class="{ active: annotationStore.tool === 'select' }" @click="annotationStore.tool = 'select'">选择</button>
          <button :class="{ active: annotationStore.tool === 'bbox' }" @click="annotationStore.tool = 'bbox'">矩形</button>
          <button @click="annotationStore.undo()">撤销</button>
          <button @click="annotationStore.redo()">重做</button>
        </div>
      </aside>
      <main>
        <AnnotationCanvas v-if="currentImageId" />
        <div v-else class="empty">请选择图像开始标注</div>
      </main>
    </div>
    <div v-if="ui.showShortcuts" class="shortcuts card">
      <h4>快捷键</h4>
      <ul>
        <li>Ctrl+Z / Ctrl+Y — 撤销/重做</li>
        <li>Ctrl+S — 保存</li>
        <li>? — 显示/隐藏此面板</li>
      </ul>
      <button @click="ui.toggleShortcuts">关闭</button>
    </div>
  </div>
</template>

<style scoped>
.annotate { height: 100vh; display: flex; flex-direction: column; }
header { display: flex; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--bg-primary); }
.meta { margin-left: 12px; color: var(--text-secondary); font-size: 13px; }
.actions { display: flex; gap: 8px; }
.body { flex: 1; display: flex; min-height: 0; }
aside { width: 280px; border-right: 1px solid var(--border); padding: 12px; overflow: auto; background: var(--bg-primary); }
main { flex: 1; min-width: 0; background: var(--bg-secondary); }
.image-list { max-height: 260px; overflow: auto; margin-bottom: 12px; }
.image-item { padding: 8px; border-bottom: 1px solid var(--border); cursor: pointer; font-size: 13px; }
.image-item.active { background: color-mix(in srgb, var(--accent) 15%, transparent); }
.labels, .tools { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.labels button { background: var(--bg-secondary); color: var(--text-primary); border: 2px solid transparent; }
.labels button.active { border-color: var(--accent); }
.tools button.active { background: #2c3e50; }
.empty { display: grid; place-items: center; height: 100%; color: var(--text-secondary); }
.shortcuts { position: fixed; right: 20px; bottom: 20px; width: 280px; z-index: 20; }
</style>
