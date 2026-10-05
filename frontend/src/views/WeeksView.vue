<template>
  <h1>Разборы по неделям</h1>
  <p v-if="loaded && empty" class="muted">Прогонов ещё нет. Запустите сбор через Collect.bat или <code>python main.py</code>. Ключевые слова можно править в разделе «<router-link to="/keywords">Ключевые слова</router-link>».</p>
  <section v-for="week in weeks" :key="week.label" class="week">
    <h2>{{ week.label }}</h2>
    <ul class="run-list">
      <li v-for="run in week.runs" :key="run.id">
        <router-link :to="'/run/' + run.id">Прогон #{{ run.id }}</router-link>
        — {{ run.started_at }}
        · <span :class="'status-' + run.status">{{ run.status }}</span>
        · lookback {{ run.lookback_days }} дн.
      </li>
    </ul>
  </section>
</template>

<script setup>
import { onMounted, ref } from "vue"

const weeks = ref([])
const empty = ref(false)
const loaded = ref(false)

onMounted(async () => {
  document.title = "Недели — AI News"
  try {
    const res = await fetch("/api/weeks")
    const data = await res.json()
    weeks.value = data.weeks || []
    empty.value = !!data.empty
  } catch (e) {
    empty.value = false
    weeks.value = []
  } finally {
    loaded.value = true
  }
})
</script>
