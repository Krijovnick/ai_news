<template>
  <header>
    <span class="brand">AI News</span>
    <router-link to="/">Недели</router-link>
    <router-link to="/keywords">Ключевые слова</router-link>
    <button
      type="button"
      class="header-menu"
      :aria-expanded="panelOpen ? 'true' : 'false'"
      @click="togglePanel"
    >Свои тексты</button>
  </header>
  <section v-if="panelOpen" class="manual-panel" aria-label="Свои тексты">
    <div v-for="(pair, index) in pairs" :key="pair.id" class="manual-pair">
      <label>
        Заголовок
        <input v-model="pair.title" type="text" :disabled="busy">
      </label>
      <label>
        Текст
        <textarea v-model="pair.text" rows="5" :disabled="busy"></textarea>
      </label>
      <button
        v-if="pairs.length > 1"
        type="button"
        class="secondary"
        :disabled="busy"
        @click="removePair(index)"
      >Убрать</button>
    </div>
    <div class="manual-actions">
      <button type="button" class="secondary" :disabled="busy" @click="addPair">Ещё</button>
      <button
        type="button"
        :class="{ 'is-busy': busy }"
        :disabled="busy || !canSubmit"
        @click="submitPairs"
      >Ок</button>
    </div>
    <p v-if="busy" class="muted">Идёт разбор…</p>
    <p v-if="errorText" class="error">{{ errorText }}</p>
  </section>
  <main>
    <router-view />
  </main>
</template>

<script setup>
import { computed, ref } from "vue"
import { useRouter } from "vue-router"

const router = useRouter()
let nextId = 1

function blankPair() {
  return { id: nextId++, title: "", text: "" }
}

const panelOpen = ref(false)
const pairs = ref([blankPair()])
const busy = ref(false)
const errorText = ref("")

const canSubmit = computed(() =>
  pairs.value.some((pair) => pair.title.trim() && pair.text.trim())
)

function togglePanel() {
  if (busy.value) return
  panelOpen.value = !panelOpen.value
  if (panelOpen.value) errorText.value = ""
}

function addPair() {
  if (busy.value) return
  pairs.value.push(blankPair())
}

function removePair(index) {
  if (busy.value || pairs.value.length <= 1) return
  pairs.value.splice(index, 1)
}

async function submitPairs() {
  if (busy.value || !canSubmit.value) return
  const items = pairs.value
    .map((pair) => ({ title: pair.title.trim(), text: pair.text.trim() }))
    .filter((pair) => pair.title && pair.text)
  busy.value = true
  errorText.value = ""
  try {
    const resp = await fetch("/api/manual-run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    })
    const data = await resp.json().catch(() => null)
    if (!resp.ok || !data || data.ok !== true || !data.run_id) {
      const message = data && data.error ? String(data.error) : "Не удалось разобрать тексты"
      errorText.value = message
      return
    }
    panelOpen.value = false
    pairs.value = [blankPair()]
    await router.push("/run/" + data.run_id)
  } catch {
    errorText.value = "Не удалось разобрать тексты"
  } finally {
    busy.value = false
  }
}
</script>
