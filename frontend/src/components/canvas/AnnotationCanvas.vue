<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import Konva from 'konva'
import { useAnnotationStore, type BBoxAnnotation } from '@/stores/annotation'
import { useCollaborationStore } from '@/stores/collaboration'
import { useProjectStore } from '@/stores/project'

const annotationStore = useAnnotationStore()
const collab = useCollaborationStore()
const projectStore = useProjectStore()

const containerRef = ref<HTMLDivElement | null>(null)
const stageRef = ref<{ getNode: () => Konva.Stage } | null>(null)
const layerRef = ref<{ getNode: () => Konva.Layer } | null>(null)
const trRef = ref<{ getNode: () => Konva.Transformer } | null>(null)

const scale = ref(1)
const imageObj = ref<HTMLImageElement | null>(null)
let drawing = false
let startPos = { x: 0, y: 0 }
let tempRect: Konva.Rect | null = null

const stageConfig = computed(() => ({
  width: containerRef.value?.clientWidth || 800,
  height: containerRef.value?.clientHeight || 600,
}))

function labelColor(labelId: string) {
  return projectStore.labels.find((l) => l.id === labelId)?.color || '#4a6fa5'
}

function labelName(labelId: string) {
  return projectStore.labels.find((l) => l.id === labelId)?.name || ''
}

function redraw() {
  const layer = layerRef.value?.getNode()
  const stage = stageRef.value?.getNode()
  const tr = trRef.value?.getNode()
  if (!layer || !stage) return

  layer.find('.ann-box').forEach((n) => n.destroy())
  tr.nodes([])

  annotationStore.annotations.forEach((ann) => {
    const rect = new Konva.Rect({
      name: 'ann-box',
      x: ann.geometry.x,
      y: ann.geometry.y,
      width: ann.geometry.width,
      height: ann.geometry.height,
      stroke: labelColor(ann.label_id),
      strokeWidth: ann.id === annotationStore.selectedId ? 3 : 2,
      fill: `${labelColor(ann.label_id)}22`,
      draggable: !annotationStore.readOnly && annotationStore.tool === 'select',
      id: ann.id,
    })
    rect.on('click', () => {
      annotationStore.selectedId = ann.id
      if (!annotationStore.readOnly) tr.nodes([rect])
      layer.batchDraw()
    })
    rect.on('dragend', () => {
      annotationStore.updateAnnotation(ann.id, {
        x: rect.x(),
        y: rect.y(),
        width: rect.width(),
        height: rect.height(),
      })
      collab.broadcastAnnotation('annotation_move', {
        image_id: annotationStore.imageId,
        annotation_id: ann.id,
        geometry: { x: rect.x(), y: rect.y(), width: rect.width(), height: rect.height() },
      })
    })
    rect.on('transformend', () => {
      const w = rect.width() * rect.scaleX()
      const h = rect.height() * rect.scaleY()
      rect.scaleX(1)
      rect.scaleY(1)
      rect.width(w)
      rect.height(h)
      annotationStore.updateAnnotation(ann.id, { x: rect.x(), y: rect.y(), width: w, height: h })
      collab.broadcastAnnotation('annotation_update', {
        image_id: annotationStore.imageId,
        annotation_id: ann.id,
        geometry: { x: rect.x(), y: rect.y(), width: w, height: h },
      })
    })
    layer.add(rect)
  })

  Object.values(collab.remoteCursors).forEach((c) => {
    const dot = new Konva.Circle({
      x: c.x,
      y: c.y,
      radius: 6,
      fill: '#f39c12',
      name: 'cursor',
    })
    layer.add(dot)
  })

  layer.batchDraw()
}

function pointerPos(stage: Konva.Stage) {
  const pos = stage.getPointerPosition()
  if (!pos) return { x: 0, y: 0 }
  const transform = stage.getAbsoluteTransform().copy().invert()
  return transform.point(pos)
}

function onStageMouseDown(e: Konva.KonvaEventObject<MouseEvent>) {
  const stage = stageRef.value?.getNode()
  const layer = layerRef.value?.getNode()
  if (!stage || !layer || annotationStore.readOnly) return

  if (annotationStore.tool === 'bbox' && annotationStore.currentLabelId) {
    drawing = true
    startPos = pointerPos(stage)
    tempRect = new Konva.Rect({
      x: startPos.x,
      y: startPos.y,
      width: 0,
      height: 0,
      stroke: labelColor(annotationStore.currentLabelId),
      dash: [4, 4],
    })
    layer.add(tempRect)
  } else if (e.target === stage) {
    annotationStore.selectedId = null
    trRef.value?.getNode().nodes([])
  }
}

function onStageMouseMove() {
  const stage = stageRef.value?.getNode()
  if (!stage || !drawing || !tempRect) return
  const pos = pointerPos(stage)
  tempRect.width(pos.x - startPos.x)
  tempRect.height(pos.y - startPos.y)
  layerRef.value?.getNode().batchDraw()
  collab.send('cursor_move', { x: pos.x, y: pos.y })
}

function onStageMouseUp() {
  const stage = stageRef.value?.getNode()
  const layer = layerRef.value?.getNode()
  if (!stage || !layer || !drawing || !tempRect) return
  drawing = false

  let { x, y, width, height } = tempRect.getClientRect({ relativeTo: layer })
  if (width < 0) { x += width; width = -width }
  if (height < 0) { y += height; height = -height }
  tempRect.destroy()
  tempRect = null

  if (width > 5 && height > 5 && annotationStore.currentLabelId) {
    const ann: BBoxAnnotation = {
      id: crypto.randomUUID(),
      type: 'bbox',
      label_id: annotationStore.currentLabelId,
      geometry: { x, y, width, height },
    }
    annotationStore.addAnnotation(ann)
    collab.broadcastAnnotation('annotation_add', { image_id: annotationStore.imageId, annotation: ann })
  }
  redraw()
}

onMounted(() => {
  if (!annotationStore.imageUrl) return
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => {
    imageObj.value = img
    const stage = stageRef.value?.getNode()
    if (!stage || !containerRef.value) return
    const s = Math.min(
      containerRef.value.clientWidth / img.width,
      containerRef.value.clientHeight / img.height,
      1,
    )
    scale.value = s
    redraw()
  }
  img.src = annotationStore.imageUrl
})

watch(() => annotationStore.annotations, redraw, { deep: true })
watch(() => annotationStore.imageUrl, () => {
  if (!annotationStore.imageUrl) return
  const img = new Image()
  img.crossOrigin = 'anonymous'
  img.onload = () => { imageObj.value = img; redraw() }
  img.src = annotationStore.imageUrl
})
</script>

<template>
  <div ref="containerRef" class="canvas-wrap">
    <v-stage
      ref="stageRef"
      :config="{ ...stageConfig, scaleX: scale, scaleY: scale }"
      @mousedown="onStageMouseDown"
      @mousemove="onStageMouseMove"
      @mouseup="onStageMouseUp"
    >
      <v-layer ref="layerRef">
        <v-image v-if="imageObj" :config="{ image: imageObj, width: annotationStore.imageWidth, height: annotationStore.imageHeight }" />
        <v-transformer ref="trRef" :config="{ rotateEnabled: false, enabledAnchors: ['top-left','top-center','top-right','middle-right','bottom-right','bottom-center','bottom-left','middle-left'] }" />
      </v-layer>
    </v-stage>
  </div>
</template>

<style scoped>
.canvas-wrap { width: 100%; height: 100%; overflow: hidden; }
</style>
