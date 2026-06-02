import { defineStore } from 'pinia'

export interface RemoteCursor {
  user_id: string
  display_name: string
  x: number
  y: number
}

export const useCollaborationStore = defineStore('collaboration', {
  state: () => ({
    connected: false,
    isEditor: false,
    onlineUsers: [] as string[],
    remoteCursors: {} as Record<string, RemoteCursor>,
    ws: null as WebSocket | null,
    heartbeatTimer: null as number | null,
  }),
  actions: {
    connect(projectId: string, token: string) {
      this.disconnect()
      const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${protocol}://${location.host}/ws/projects/${projectId}?token=${token}`)
      this.ws = ws
      ws.onopen = () => {
        this.connected = true
        this.heartbeatTimer = window.setInterval(() => {
          this.send('ping', {})
        }, 25000)
      }
      ws.onclose = () => {
        this.connected = false
        if (this.heartbeatTimer) clearInterval(this.heartbeatTimer)
      }
      return ws
    },
    disconnect() {
      if (this.ws) this.ws.close()
      this.ws = null
      this.connected = false
    },
    send(type: string, payload: Record<string, unknown>) {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return
      this.ws.send(JSON.stringify({ type, payload }))
    },
    joinImage(imageId: string) {
      this.send('join_image', { image_id: imageId })
    },
    leaveImage(imageId: string) {
      this.send('leave_image', { image_id: imageId })
    },
    broadcastAnnotation(type: string, payload: Record<string, unknown>) {
      if (!this.isEditor) return
      this.send(type, payload)
    },
  },
})
