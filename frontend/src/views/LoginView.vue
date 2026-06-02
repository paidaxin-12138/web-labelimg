<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const email = ref('admin@example.com')
const password = ref('admin123')
const displayName = ref('')
const mode = ref<'login' | 'register'>('login')
const error = ref('')

async function submit() {
  error.value = ''
  try {
    if (mode.value === 'login') await auth.login(email.value, password.value)
    else await auth.register(email.value, password.value, displayName.value)
    router.push('/')
  } catch (e: unknown) {
    error.value = '登录失败，请检查账号密码'
  }
}
</script>

<template>
  <div class="login-page">
    <div class="card login-card">
      <h1>Web LabelImg 2.0</h1>
      <p class="sub">可协作图像标注平台</p>
      <div v-if="mode === 'register'" class="field">
        <label>显示名称</label>
        <input v-model="displayName" />
      </div>
      <div class="field">
        <label>邮箱</label>
        <input v-model="email" type="email" />
      </div>
      <div class="field">
        <label>密码</label>
        <input v-model="password" type="password" />
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <button @click="submit">{{ mode === 'login' ? '登录' : '注册' }}</button>
      <button class="link" @click="mode = mode === 'login' ? 'register' : 'login'">
        {{ mode === 'login' ? '没有账号？注册' : '已有账号？登录' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.login-page { min-height: 100vh; display: grid; place-items: center; }
.login-card { width: 380px; display: flex; flex-direction: column; gap: 12px; }
.sub { color: var(--text-secondary); margin-bottom: 8px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.error { color: var(--danger); }
.link { background: transparent; color: var(--accent); }
</style>
