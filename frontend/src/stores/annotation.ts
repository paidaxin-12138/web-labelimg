import { defineStore } from 'pinia'

export interface BBoxAnnotation {
  id: string
  type: 'bbox'
  label_id: string
  geometry: { x: number; y: number; width: number; height: number }
}

interface Snapshot {
  annotations: BBoxAnnotation[]
  selectedId: string | null
}

const MAX_HISTORY = 50

export const useAnnotationStore = defineStore('annotation', {
  state: () => ({
    imageId: null as string | null,
    imageWidth: 0,
    imageHeight: 0,
    imageUrl: '',
    baseVersion: 0,
    annotations: [] as BBoxAnnotation[],
    selectedId: null as string | null,
    currentLabelId: null as string | null,
    tool: 'select' as 'select' | 'bbox',
    readOnly: false,
    undoStack: [] as Snapshot[],
    redoStack: [] as Snapshot[],
    remoteApplying: false,
  }),
  actions: {
    snapshot(): Snapshot {
      return {
        annotations: JSON.parse(JSON.stringify(this.annotations)),
        selectedId: this.selectedId,
      }
    },
    pushHistory() {
      if (this.remoteApplying) return
      this.undoStack.push(this.snapshot())
      if (this.undoStack.length > MAX_HISTORY) this.undoStack.shift()
      this.redoStack = []
    },
    undo() {
      if (!this.undoStack.length) return
      this.redoStack.push(this.snapshot())
      const prev = this.undoStack.pop()!
      this.annotations = prev.annotations
      this.selectedId = prev.selectedId
    },
    redo() {
      if (!this.redoStack.length) return
      this.undoStack.push(this.snapshot())
      const next = this.redoStack.pop()!
      this.annotations = next.annotations
      this.selectedId = next.selectedId
    },
    resetHistory() {
      this.undoStack = []
      this.redoStack = []
    },
    setFromServer(payload: {
      imageId: string
      imageWidth: number
      imageHeight: number
      imageUrl: string
      baseVersion: number
      annotations: BBoxAnnotation[]
    }) {
      this.imageId = payload.imageId
      this.imageWidth = payload.imageWidth
      this.imageHeight = payload.imageHeight
      this.imageUrl = payload.imageUrl
      this.baseVersion = payload.baseVersion
      this.annotations = payload.annotations
      this.selectedId = null
      this.resetHistory()
    },
    addAnnotation(ann: BBoxAnnotation) {
      this.pushHistory()
      this.annotations.push(ann)
    },
    updateAnnotation(id: string, patch: Partial<BBoxAnnotation['geometry']>) {
      const target = this.annotations.find((a) => a.id === id)
      if (!target) return
      this.pushHistory()
      target.geometry = { ...target.geometry, ...patch }
    },
    deleteAnnotation(id: string) {
      this.pushHistory()
      this.annotations = this.annotations.filter((a) => a.id !== id)
      if (this.selectedId === id) this.selectedId = null
    },
    applyRemote(type: string, payload: Record<string, unknown>) {
      this.remoteApplying = true
      try {
        if (type === 'annotation_add') {
          const ann = payload.annotation as BBoxAnnotation
          const idx = this.annotations.findIndex((a) => a.id === ann.id)
          if (idx >= 0) this.annotations[idx] = ann
          else this.annotations.push(ann)
        } else if (type === 'annotation_update' || type === 'annotation_move') {
          const id = payload.annotation_id as string
          const target = this.annotations.find((a) => a.id === id)
          if (target && payload.geometry) target.geometry = payload.geometry as BBoxAnnotation['geometry']
        } else if (type === 'annotation_delete') {
          this.annotations = this.annotations.filter((a) => a.id !== payload.annotation_id)
        }
      } finally {
        this.remoteApplying = false
      }
    },
  },
})
