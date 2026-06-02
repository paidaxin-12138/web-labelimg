import { defineStore } from 'pinia'
import api from '@/services/api'

export interface Project {
  id: string
  name: string
  description?: string
  status: string
}

export interface LabelItem {
  id: string
  class_id: number
  name: string
  color: string
}

export interface ImageItem {
  id: string
  filename: string
  url?: string
  thumbnail_url?: string
  width: number
  height: number
  status: string
  version: number
}

export const useProjectStore = defineStore('project', {
  state: () => ({
    projects: [] as Project[],
    currentProject: null as Project | null,
    labels: [] as LabelItem[],
    images: [] as ImageItem[],
    imageTotal: 0,
  }),
  actions: {
    async loadProjects() {
      const { data } = await api.get('/projects')
      this.projects = data
    },
    async createProject(name: string, description?: string) {
      const { data } = await api.post('/projects', { name, description })
      this.projects.unshift(data)
      return data
    },
    async selectProject(projectId: string) {
      this.currentProject = this.projects.find((p) => p.id === projectId) || null
      await Promise.all([this.loadLabels(projectId), this.loadImages(projectId)])
    },
    async loadLabels(projectId: string) {
      const { data } = await api.get(`/projects/${projectId}/labels`)
      this.labels = data
    },
    async loadImages(projectId: string, page = 1) {
      const { data } = await api.get(`/projects/${projectId}/images`, { params: { page, page_size: 50 } })
      this.images = data.items
      this.imageTotal = data.total
    },
    async uploadImages(projectId: string, files: FileList) {
      const form = new FormData()
      Array.from(files).forEach((f) => form.append('files', f))
      await api.post(`/projects/${projectId}/images/upload`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      await this.loadImages(projectId)
    },
    async exportYolo(projectId: string) {
      const { data } = await api.post(`/projects/${projectId}/exports`, { format: 'yolo' })
      return data
    },
  },
})
