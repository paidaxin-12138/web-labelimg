import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { useAnnotationStore } from '@/stores/annotation'

describe('annotation undo/redo', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('supports undo and redo', () => {
    const store = useAnnotationStore()
    store.setFromServer({
      imageId: '1',
      imageWidth: 100,
      imageHeight: 100,
      imageUrl: '',
      baseVersion: 0,
      annotations: [],
    })

    store.addAnnotation({
      id: 'a1',
      type: 'bbox',
      label_id: 'l1',
      geometry: { x: 1, y: 2, width: 3, height: 4 },
    })
    expect(store.annotations).toHaveLength(1)

    store.undo()
    expect(store.annotations).toHaveLength(0)

    store.redo()
    expect(store.annotations).toHaveLength(1)
  })
})
