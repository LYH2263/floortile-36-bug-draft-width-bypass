<script setup>
import { onMounted, ref } from 'vue'
import { getJSON, postJSON } from '../api'
const props = defineProps({ id: String })
const room = ref(null)
const width = ref(null)
const msg = ref('')
async function load() {
  room.value = await getJSON(`/api/rooms/${props.id}`)
  width.value = room.value.width
}
onMounted(load)
async function saveWidth() {
  msg.value = ''
  // patch via fetch wrapper if available; fall back to postJSON-compatible call
  try {
    const res = await fetch(`/api/rooms/${props.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ width: Number(width.value) }),
    })
    room.value = await res.json()
    msg.value = '宽度已更新'
  } catch (e) {
    msg.value = e.message || String(e)
  }
}
</script>
<template>
  <div class="page" v-if="room">
    <h1>{{ room.name }}</h1>
    <div v-if="room.data_quality === 'dirty'" class="alert">该房间尺寸异常：{{ room.note }}</div>
    <dl>
      <dt>长度</dt><dd>{{ room.length }} m</dd>
      <dt>宽度</dt>
      <dd>
        <input type="number" v-model.number="width" step="0.1" min="0.1" /> m
        <button @click="saveWidth">只改宽度</button>
      </dd>
      <dt>面积</dt><dd>{{ (room.length * room.width).toFixed(2) }} m²</dd>
    </dl>
    <p v-if="msg" class="hint">{{ msg }}</p>
    <router-link to="/bench">去测算</router-link>
  </div>
</template>
