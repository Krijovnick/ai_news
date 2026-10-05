<template>
  <p v-if="notFound">Прогон не найден</p>
  <template v-else-if="run">
    <p><router-link to="/">← К неделям</router-link></p>
    <h1>Прогон #{{ run.id }}</h1>
    <p>
      Статус: <strong :class="'status-' + run.status">{{ run.status }}</strong><br>
      Начало: {{ run.started_at }}<br>
      Конец: {{ run.finished_at || "—" }}<br>
      Lookback: {{ run.lookback_days }} дн.<br>
      Telegram: {{ run.telegram_sent ? "отправлено" : "нет" }}
    </p>

    <template v-if="run.error_text">
      <h2>Протокол ошибок / пометок</h2>
      <div class="protocol">{{ run.error_text }}</div>
    </template>

    <h2>Разбор</h2>
    <div v-if="summary" class="summary">{{ summary }}</div>
    <p v-else class="muted">Разбора нет.</p>

    <h2>Статьи</h2>
    <ul v-if="articles.length">
      <li v-for="article in articles" :key="article.id">
        <router-link :to="'/article/' + article.id">{{ article.title }}</router-link>
      </li>
    </ul>
    <p v-else class="muted">Статей нет.</p>
  </template>
</template>

<script setup>
import { ref, watch } from "vue"
import { useRoute } from "vue-router"

const route = useRoute()
const run = ref(null)
const summary = ref("")
const articles = ref([])
const notFound = ref(false)

async function load() {
  run.value = null
  summary.value = ""
  articles.value = []
  notFound.value = false
  document.title = "AI News"
  try {
    const res = await fetch("/api/runs/" + route.params.id)
    const data = await res.json()
    if (res.status === 404 || !data.run) {
      notFound.value = true
      return
    }
    run.value = data.run
    summary.value = data.summary || ""
    articles.value = data.articles || []
    document.title = "Прогон #" + data.run.id + " — AI News"
  } catch (e) {
    notFound.value = true
  }
}

watch(() => route.params.id, load, { immediate: true })
</script>
